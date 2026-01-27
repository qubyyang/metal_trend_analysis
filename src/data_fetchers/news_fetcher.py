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


class NewsFetcher:
    """News Fetcher"""

    def __init__(self, config: Dict[str, Any], sources: List[Dict[str, Any]], keywords: List[str]):
        """
        Initialize News Fetcher

        Args:
            config: 新闻配置
            sources: 新闻源配置列表
            keywords: 关键词列表
        """
        self.enabled = config.get('enabled', True)
        self.max_articles = config.get('max_articles', 10)
        self.cache_duration = config.get('cache_duration', 300)  # 秒

        self.sources = sources
        self.keywords = [k.lower() for k in keywords]

        self.fetch_config = config.get('fetch', {
            'timeout': 15,
            'delay': 2,
            'max_retries': 3
        })

        # 缓存
        self.cache_file = Path('data/cache/news_cache.json')
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict[str, Any]:
        """加载缓存"""
        if self.cache_file.exists():
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        """保存缓存"""
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False

        cached_time = datetime.fromisoformat(self.cache[cache_key]['timestamp'])
        expiry_time = cached_time + timedelta(seconds=self.cache_duration)

        return datetime.now() < expiry_time

    def _filter_by_keywords(self, title: str, content: str) -> bool:
        """
        根据关键词过滤新闻

        Args:
            title: 新闻标题
            content: 新闻内容

        Returns:
            是否匹配关键词
        """
        text = (title + ' ' + content).lower()

        # 如果没有关键词，返回所有新闻
        if not self.keywords:
            return True

        # 检查是否包含任一关键词
        for keyword in self.keywords:
            if keyword in text:
                return True

        return False

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

    def fetch_all_news(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        从所有启用的新闻源抓取新闻

        Args:
            use_cache: 是否使用缓存

        Returns:
            所有新闻列表
        """
        if not self.enabled:
            return []

        cache_key = 'all_news'

        # 检查缓存
        if use_cache and self._is_cache_valid(cache_key):
            return self.cache[cache_key]['articles']

        all_articles = []

        for source in self.sources:
            if not source.get('enabled', True):
                continue

            # 根据类型选择抓取方法
            if source['type'] == 'rss':
                articles = self._fetch_rss(source)
            elif source['type'] == 'api':
                articles = self._fetch_api(source)
            else:
                print(f"未知的新闻源类型: {source['type']}")
                continue

            all_articles.extend(articles)

            # 请求延迟
            time.sleep(self.fetch_config['delay'])

        # 按发布时间排序
        all_articles.sort(key=lambda x: x['published'], reverse=True)

        # 更新缓存
        self.cache[cache_key] = {
            'timestamp': datetime.now().isoformat(),
            'articles': all_articles
        }
        self._save_cache()

        return all_articles[:self.max_articles]

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
            title = article['title']
            source = article['source']
            summary_lines.append(f"{i}. [{source}] {title}")

        summary = '\n'.join(summary_lines)

        # 截断到指定长度
        if len(summary) > max_chars:
            summary = summary[:max_chars] + '...'

        return summary
