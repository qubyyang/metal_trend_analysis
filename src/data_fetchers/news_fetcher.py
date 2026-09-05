"""
News Fetcher Module
"""
import requests
import feedparser
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time
from pathlib import Path
import json
import re
from loguru import logger

from .news_sources import get_news_sources_from_config
from ..utils.exceptions import DataFetchError, NetworkError, ValidationError
from ..utils.common import with_retry, validate_config, safe_execute


class NewsFetcher:
    """News Fetcher"""

    def __init__(self, config: Dict[str, Any], sources: List[Dict[str, Any]] = None, keywords: List[str] = None):
        """
        Initialize News Fetcher

        Args:
            config: 新闻配置
            sources: 新闻源配置列表 (可选，如果不提供则从config读取)
            keywords: 关键词列表

        Raises:
            ValidationError: 配置无效时抛出
        """
        self.logger = logger.bind(name=self.__class__.__name__)

        # Validate basic config
        validate_config(config, [], "News fetcher config")

        # 从配置读取设置
        self.enabled = config.get('enabled', True)
        self.max_articles = config.get('max_articles', 10)
        self.cache_duration = config.get('cache_duration', 300)

        # 获取新闻源配置
        if sources is None:
            self.sources = safe_execute(
                lambda: get_news_sources_from_config(config, enabled_only=True),
                default_value=[],
                logger_name="news_sources"
            )
        else:
            self.sources = sources

        # 关键词
        self.keywords = [k.lower() for k in keywords] if keywords else []

        # Fetch配置
        fetch_config = config.get('fetch', {})
        self.fetch_config = {
            'timeout': fetch_config.get('timeout', 15),
            'delay': fetch_config.get('delay', 2),
            'max_retries': fetch_config.get('max_retries', 3)
        }

        # 缓存
        self.cache_file = Path('data/cache/news_cache.json')
        self.cache = self._load_cache()

        self.logger.info(f"News fetcher initialized with {len(self.sources)} sources and {len(self.keywords)} keywords")

    def _load_cache(self) -> Dict[str, Any]:
        """
        加载缓存

        Returns:
            缓存字典，加载失败时返回空字典
        """
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    self.logger.debug(f"Loaded cache with {len(cache_data)} entries")
                    return cache_data
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {e}")

        return {}

    def _save_cache(self) -> bool:
        """
        保存缓存

        Returns:
            是否保存成功
        """
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            self.logger.debug("Cache saved successfully")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save cache: {e}")
            return False

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        检查缓存是否有效

        Args:
            cache_key: 缓存键

        Returns:
            缓存是否有效
        """
        try:
            if cache_key not in self.cache:
                return False

            cached_time = datetime.fromisoformat(self.cache[cache_key]['timestamp'])
            expiry_time = cached_time + timedelta(seconds=self.cache_duration)

            is_valid = datetime.now() < expiry_time
            if not is_valid:
                self.logger.debug(f"Cache expired for key: {cache_key}")

            return is_valid

        except Exception as e:
            self.logger.warning(f"Error checking cache validity for {cache_key}: {e}")
            return False

    def _filter_by_keywords(self, title: str, content: str) -> bool:
        """
        根据关键词过滤新闻

        Args:
            title: 新闻标题
            content: 新闻内容

        Returns:
            是否匹配关键词
        """
        if not self.keywords:
            return True

        try:
            text = f"{title} {content}".lower()
            return any(keyword in text for keyword in self.keywords)
        except Exception as e:
            self.logger.warning(f"Error filtering by keywords: {e}")
            return True

    @with_retry(max_attempts=3, exceptions=(NetworkError, requests.RequestException))
    def _fetch_rss_feed(self, url: str) -> List[Dict[str, Any]]:
        """
        获取 RSS 源新闻

        Args:
            url: RSS 源 URL

        Returns:
            新闻列表

        Raises:
            NetworkError: 网络请求失败
            DataFetchError: 数据解析失败
        """
        try:
            self.logger.debug(f"Fetching RSS feed: {url}")

            response = requests.get(
                url,
                timeout=self.fetch_config['timeout'],
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            response.raise_for_status()

            feed = feedparser.parse(response.text)
            if not feed.entries:
                self.logger.warning(f"No entries found in RSS feed: {url}")
                return []

            articles = []
            for entry in feed.entries[:self.max_articles]:
                try:
                    # 提取新闻信息
                    title = getattr(entry, 'title', '').strip()
                    content = getattr(entry, 'summary', '').strip()
                    link = getattr(entry, 'link', '').strip()
                    published = getattr(entry, 'published', '')

                    if not title:
                        continue

                    # 清理HTML标签
                    content = re.sub(r'<[^>]+>', '', content)

                    # 解析发布时间
                    published_time = None
                    if published:
                        try:
                            published_time = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %Z').isoformat()
                        except:
                            try:
                                published_time = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %z').isoformat()
                            except:
                                published_time = datetime.now().isoformat()

                    # 关键词过滤
                    if not self._filter_by_keywords(title, content):
                        continue

                    articles.append({
                        'title': title,
                        'content': content,
                        'link': link,
                        'published': published_time or datetime.now().isoformat(),
                        'source_url': url
                    })

                except Exception as e:
                    self.logger.warning(f"Error processing RSS entry: {e}")
                    continue

            self.logger.info(f"Fetched {len(articles)} articles from RSS: {url}")
            return articles

        except requests.RequestException as e:
            raise NetworkError(f"Network error fetching RSS feed {url}: {e}")
        except Exception as e:
            raise DataFetchError(f"Error parsing RSS feed {url}: {e}")

    def fetch_news_from_source(self, source: Dict[str, Any], use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        从单个新闻源获取新闻

        Args:
            source: 新闻源配置
            use_cache: 是否使用缓存

        Returns:
            新闻列表
        """
        try:
            url = source.get('url', '')
            if not url:
                raise ValidationError("News source missing URL")

            source_name = source.get('name', url)
            cache_key = f"news_{source_name}_{url}"

            # 检查缓存
            if use_cache and self._is_cache_valid(cache_key):
                cached_articles = self.cache[cache_key].get('articles', [])
                self.logger.debug(f"Using cached articles for {source_name}: {len(cached_articles)} articles")
                return cached_articles

            # 获取新闻
            articles = []
            source_type = source.get('type', 'rss')

            if source_type == 'rss':
                articles = self._fetch_rss_feed(url)
            elif source_type == 'api':
                articles = self._fetch_api(source)
            elif source_type == 'html':
                articles = self._fetch_html(source)
            else:
                self.logger.warning(f"Unsupported source type: {source_type}")

            # 缓存结果
            if articles:
                self.cache[cache_key] = {
                    'articles': articles,
                    'timestamp': datetime.now().isoformat()
                }
                self._save_cache()

            self.logger.info(f"Fetched {len(articles)} articles from {source_name}")
            return articles

        except (NetworkError, DataFetchError, ValidationError):
            raise
        except Exception as e:
            raise DataFetchError(f"Unexpected error fetching news from {source.get('name', 'unknown')}: {e}")

    def fetch_all_news(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        获取所有新闻源的新闻

        Args:
            use_cache: 是否使用缓存

        Returns:
            所有新闻列表
        """
        if not self.enabled:
            self.logger.info("News fetching is disabled")
            return []

        if not self.sources:
            self.logger.warning("No news sources configured")
            return []

        all_articles = []

        for source in self.sources:
            if not source.get('enabled', True):
                continue

            try:
                source_name = source.get('name', 'unknown')
                self.logger.debug(f"Fetching news from: {source_name}")

                articles = self.fetch_news_from_source(source, use_cache)
                all_articles.extend(articles)

                # 添加延时避免请求过快
                if self.fetch_config['delay'] > 0:
                    time.sleep(self.fetch_config['delay'])

            except Exception as e:
                source_name = source.get('name', 'unknown')
                self.logger.error(f"Failed to fetch news from {source_name}: {e}")
                continue

        # 按发布时间排序（最新的在前）
        try:
            all_articles.sort(
                key=lambda x: datetime.fromisoformat(x.get('published', datetime.now().isoformat())),
                reverse=True
            )
        except Exception as e:
            self.logger.warning(f"Error sorting articles by time: {e}")

        # 限制文章数量
        if len(all_articles) > self.max_articles:
            all_articles = all_articles[:self.max_articles]

        self.logger.info(f"Total articles fetched: {len(all_articles)}")
        return all_articles

    def _fetch_rss(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 RSS 源抓取新闻

        Args:
            source: 新闻源配置

        Returns:
            新闻列表
        """
        articles = []

        try:
            headers = source.get('headers', {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

            # 获取 RSS 内容
            response = requests.get(
                source['url'],
                headers=headers,
                timeout=self.fetch_config['timeout']
            )
            response.raise_for_status()

            # 解析 RSS
            feed = feedparser.parse(response.content)

            for entry in feed.entries[:self.max_articles]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                published = entry.get('published', '')
                summary = entry.get('summary', entry.get('description', ''))

                # 关键词过滤
                if self._filter_by_keywords(title, summary):
                    articles.append({
                        'source': source['name'],
                        'title': title,
                        'link': link,
                        'published': published,
                        'content': summary,
                        'timestamp': datetime.now().isoformat()
                    })

        except Exception as e:
            print(f"RSS 抓取失败 {source['name']}: {str(e)}")

        return articles

    def _fetch_api(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 API 源抓取新闻

        Args:
            source: 新闻源配置

        Returns:
            新闻列表
        """
        articles = []

        try:
            headers = source.get('headers', {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

            params = source.get('params', {})

            response = requests.get(
                source['url'],
                headers=headers,
                params=params,
                timeout=self.fetch_config['timeout']
            )
            response.raise_for_status()

            data = response.json()

            # 解析 API 数据（根据具体 API 格式调整）
            if 'data' in data and isinstance(data['data'], list):
                for item in data['data'][:self.max_articles]:
                    title = item.get('title', '')
                    link = item.get('url', item.get('link', ''))
                    published = item.get('time', item.get('published', ''))
                    content = item.get('content', item.get('description', ''))

                    # 关键词过滤
                    if self._filter_by_keywords(title, content):
                        articles.append({
                            'source': source['name'],
                            'title': title,
                            'link': link,
                            'published': published,
                            'content': content,
                            'timestamp': datetime.now().isoformat()
                        })

        except Exception as e:
            print(f"API 抓取失败 {source['name']}: {str(e)}")

        return articles

    def _fetch_html(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 HTML/Markdown 源抓取新闻（常用于无 RSS 的站点）

        Args:
            source: 新闻源配置

        Returns:
            新闻列表
        """
        articles: List[Dict[str, Any]] = []

        try:
            headers = source.get('headers', {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })

            response = requests.get(
                source['url'],
                headers=headers,
                timeout=self.fetch_config['timeout']
            )
            response.raise_for_status()

            parser = source.get('parser', 'markdown_links')
            text = response.text

            if parser == 'cls_telegraph':
                for line in text.splitlines():
                    match = re.search(r'\*\*【(.+?)】\*\*', line)
                    if not match:
                        continue

                    title = match.group(1).strip()
                    content = re.sub(r'^\d{2}:\d{2}:\d{2}\s*', '', line).strip()

                    if not self._filter_by_keywords(title, content):
                        continue

                    articles.append({
                        'source': source['name'],
                        'title': title,
                        'link': source.get('link', source['url']),
                        'published': datetime.now().isoformat(),
                        'content': content,
                        'timestamp': datetime.now().isoformat()
                    })

            elif parser == 'markdown_links':
                link_contains = source.get('link_contains', [])
                link_contains = [item.lower() for item in link_contains]

                for title, link in re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', text):
                    clean_title = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', title).strip()
                    if not clean_title:
                        continue
                    if clean_title.startswith('!') or clean_title.lower().startswith('image'):
                        continue
                    if link.startswith('blob:') or link.startswith('javascript:'):
                        continue

                    if link_contains:
                        link_lower = link.lower()
                        if not any(item in link_lower for item in link_contains):
                            continue

                    if not self._filter_by_keywords(clean_title, ''):
                        continue

                    articles.append({
                        'source': source['name'],
                        'title': clean_title,
                        'link': link,
                        'published': datetime.now().isoformat(),
                        'content': clean_title,
                        'timestamp': datetime.now().isoformat()
                    })

            else:
                print(f"未知的 HTML 解析器: {parser}")

        except Exception as e:
            print(f"HTML 抓取失败 {source['name']}: {str(e)}")

        return articles[:self.max_articles]


    def get_news_summary(self, articles: List[Dict[str, Any]], max_chars: int = 500) -> str:
        """
        生成新闻摘要

        Args:
            articles: 新闻列表
            max_chars: 最大字符数

        Returns:
            新闻摘要文本
        """
        if not articles:
            return "暂无相关新闻"

        summary_lines = []

        for i, article in enumerate(articles[:5], 1):  # 最多 5 条
            title = article.get('title', '(无标题)')
            source = article.get('source', '未知来源')
            summary_lines.append(f"{i}. [{source}] {title}")

        summary = '\n'.join(summary_lines)

        # 截断到指定长度
        if len(summary) > max_chars:
            summary = summary[:max_chars] + '...'

        return summary
