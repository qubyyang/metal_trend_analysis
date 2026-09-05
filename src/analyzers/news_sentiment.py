"""
News Sentiment Analyzer Module
"""
import re
from typing import Dict, List, Any, Tuple
from collections import Counter


class NewsSentimentAnalyzer:
    """News Sentiment Analyzer"""

    def __init__(self):
        """Initialize sentiment analyzer"""
        # 正面词汇 (包含中文和英文)
        self.positive_words = {
            # 中文正面词汇
            '上涨', '攀升', '突破', '强势', '利好', '推动', '支撑', '反弹',
            '上涨', '走高', '收涨', '报涨', '涨', '升', '增', '稳', '坚挺',
            '复苏', '回升', '提振', '乐观', '积极', '向好', '看涨', '牛市',
            '买盘', '需求', '避险', '保值', '涨势', '升势', '上涨动力',
            # 英文正面词汇
            'rise', 'rises', 'rising', 'increase', 'increases', 'increasing',
            'gain', 'gains', 'gaining', 'surge', 'surges', 'surging',
            'climb', 'climbs', 'climbing', 'rally', 'rallies', 'rallied',
            'rally', 'bullish', 'positive', 'optimistic', 'support', 'supports',
            'supported', 'breakout', 'breakouts', 'breakthrough', 'breakthroughs',
            'strong', 'strength', 'strengthens', 'recovery', 'recoveries',
            'upward', 'uptrend', 'gains momentum', 'momentum', 'soar', 'soars',
            'surge', 'skyrocket', 'skyrockets', 'jump', 'jumps', 'jumped',
            'boost', 'boosts', 'boosted', 'buys', 'buying', 'demand',
            'demand', 'haven', 'safe haven', 'preserve', 'value', 'rally',
            'advance', 'advances', 'advancing', 'higher', 'highs', 'high',
            'favorable', 'good', 'great', 'excellent', 'outperform'
        }

        # 负面词汇
        self.negative_words = {
            # 中文负面词汇
            '下跌', '暴跌', '大跌', '下滑', '回落', '走弱', '利空', '打压',
            '阻力', '压制', '下跌', '走低', '收跌', '报跌', '跌', '降', '减',
            '疲软', '疲弱', '担忧', '悲观', '消极', '向淡', '看跌', '熊市',
            '卖盘', '供给', '供应', '过剩', '跌势', '跌势', '下跌压力',
            '风险', '下跌', '暴跌', '崩盘', '下跌', '下跌', '暴跌',
            # 英文负面词汇
            'fall', 'falls', 'falling', 'drop', 'drops', 'dropping',
            'decline', 'declines', 'declining', 'plunge', 'plunges', 'plunging',
            'slump', 'slumps', 'slumped', 'crash', 'crashes', 'crashed',
            'bearish', 'negative', 'pessimistic', 'resistance', 'resistances',
            'pressured', 'pressure', 'weak', 'weakness', 'weakens', 'weakness',
            'concern', 'concerns', 'concerned', 'worry', 'worries', 'worried',
            'downturn', 'downturns', 'downward', 'downtrend', 'sell',
            'sells', 'selling', 'sell-off', 'sell-offs', 'supply', 'supplied',
            'supplies', 'excess', 'risk', 'risks', 'risky', 'danger',
            'threat', 'threatens', 'threatening', 'collapse', 'collapses',
            'collapsed', 'lower', 'lows', 'low', 'unfavorable', 'bad', 'poor',
            'underperform', 'underperforms', 'underperformed'
        }

        # 中性/不确定性词汇
        self.neutral_words = {
            '持平', '震荡', '波动', '横盘', '盘整', '观望', '等待',
            '持平', '不变', '持平', '震荡', '盘整', '波动', '观望',
            'stable', 'flat', 'sideways', 'range', 'volatile', 'volatility',
            'uncertain', 'uncertainty', 'waiting', 'wait', 'watch', 'monitor'
        }

    def analyze_text_sentiment(self, text: str) -> Dict[str, Any]:
        """
        分析单条新闻的情感倾向

        Args:
            text: 新闻文本（标题+内容）

        Returns:
            情感分析结果字典
        """
        text_lower = text.lower()

        # 统计各类词汇出现次数
        positive_count = 0
        negative_count = 0
        neutral_count = 0

        matched_positive = []
        matched_negative = []
        matched_neutral = []

        # 检查正面词汇
        for word in self.positive_words:
            if word in text_lower:
                positive_count += text_lower.count(word)
                if word not in matched_positive:
                    matched_positive.append(word)

        # 检查负面词汇
        for word in self.negative_words:
            if word in text_lower:
                negative_count += text_lower.count(word)
                if word not in matched_negative:
                    matched_negative.append(word)

        # 检查中性词汇
        for word in self.neutral_words:
            if word in text_lower:
                neutral_count += text_lower.count(word)
                if word not in matched_neutral:
                    matched_neutral.append(word)

        # 计算情感分数
        total_words = positive_count + negative_count + neutral_count

        if total_words == 0:
            sentiment = 'neutral'
            confidence = 0.0
            score = 0.0
        else:
            # 情感分数 = (正面 - 负面) / 总数
            score = (positive_count - negative_count) / total_words

            # 确定情感倾向
            if score > 0.2:
                sentiment = 'bullish'
            elif score < -0.2:
                sentiment = 'bearish'
            else:
                sentiment = 'neutral'

            # 置信度
            confidence = abs(score)

        return {
            'sentiment': sentiment,
            'score': score,
            'confidence': confidence,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'neutral_count': neutral_count,
            'matched_positive': matched_positive,
            'matched_negative': matched_negative,
            'matched_neutral': matched_neutral
        }

    def analyze_articles_sentiment(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析多篇新闻的整体情感倾向

        Args:
            articles: 新闻文章列表

        Returns:
            整体情感分析结果
        """
        if not articles:
            return {
                'overall_sentiment': 'neutral',
                'overall_score': 0.0,
                'total_articles': 0,
                'bullish_count': 0,
                'bearish_count': 0,
                'neutral_count': 0,
                'top_bullish_articles': [],
                'top_bearish_articles': [],
                'key_themes': []
            }

        results = []

        # 分析每篇文章
        for article in articles:
            text = article.get('title', '') + ' ' + article.get('content', '')
            sentiment_result = self.analyze_text_sentiment(text)

            article_analysis = {
                'article': article,
                'sentiment': sentiment_result['sentiment'],
                'score': sentiment_result['score'],
                'confidence': sentiment_result['confidence']
            }

            results.append(article_analysis)

        # 统计各类文章数量
        bullish_count = sum(1 for r in results if r['sentiment'] == 'bullish')
        bearish_count = sum(1 for r in results if r['sentiment'] == 'bearish')
        neutral_count = sum(1 for r in results if r['sentiment'] == 'neutral')

        # 计算整体情感分数（加权平均）
        if results:
            avg_score = sum(r['score'] for r in results) / len(results)
        else:
            avg_score = 0.0

        # 确定整体情感倾向
        if avg_score > 0.1:
            overall_sentiment = 'bullish'
        elif avg_score < -0.1:
            overall_sentiment = 'bearish'
        else:
            overall_sentiment = 'neutral'

        # 获取最积极和最消极的文章（按分数排序）
        sorted_by_score = sorted(results, key=lambda x: x['score'], reverse=True)
        top_bullish_articles = sorted_by_score[:3]  # 前3篇最积极的
        top_bearish_articles = sorted_by_score[-3:]  # 后3篇最消极的
        top_bearish_articles.reverse()  # 按从消极到轻微消极排序

        # 提取关键主题（汇总所有匹配的词汇）
        all_positive_words = []
        all_negative_words = []

        for r in results:
            for article in articles:
                text = article.get('title', '') + ' ' + article.get('content', '')
                text_lower = text.lower()
                for word in self.positive_words:
                    if word in text_lower:
                        all_positive_words.append(word)
                for word in self.negative_words:
                    if word in text_lower:
                        all_negative_words.append(word)

        # 统计出现频率最高的词汇
        key_themes = []
        if all_positive_words:
            positive_counter = Counter(all_positive_words)
            key_themes.extend([f"积极: {word}" for word, _ in positive_counter.most_common(3)])
        if all_negative_words:
            negative_counter = Counter(all_negative_words)
            key_themes.extend([f"消极: {word}" for word, _ in negative_counter.most_common(3)])

        return {
            'overall_sentiment': overall_sentiment,
            'overall_score': avg_score,
            'total_articles': len(articles),
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'neutral_count': neutral_count,
            'bullish_percentage': (bullish_count / len(articles)) * 100 if articles else 0,
            'bearish_percentage': (bearish_count / len(articles)) * 100 if articles else 0,
            'neutral_percentage': (neutral_count / len(articles)) * 100 if articles else 0,
            'top_bullish_articles': top_bullish_articles,
            'top_bearish_articles': top_bearish_articles,
            'key_themes': key_themes
        }

    def get_sentiment_summary(self, sentiment_result: Dict[str, Any]) -> str:
        """
        生成情感分析的摘要文本

        Args:
            sentiment_result: 情感分析结果

        Returns:
            摘要文本
        """
        overall_sentiment = sentiment_result.get('overall_sentiment', 'neutral')
        total = sentiment_result.get('total_articles', 0)
        bullish = sentiment_result.get('bullish_count', 0)
        bearish = sentiment_result.get('bearish_count', 0)
        neutral = sentiment_result.get('neutral_count', 0)
        score = sentiment_result.get('overall_score', 0.0)

        # 翻译情感倾向
        sentiment_map = {
            'bullish': '看涨',
            'bearish': '看跌',
            'neutral': '中性'
        }

        # 生成摘要
        summary = f"""
## 📰 新闻情感分析

**整体倾向**: {sentiment_map.get(overall_sentiment, '未知')} (分数: {score:.2f})

**文章统计**:
- 总文章数: {total}
- 看涨: {bullish} ({sentiment_result.get('bullish_percentage', 0):.1f}%)
- 看跌: {bearish} ({sentiment_result.get('bearish_percentage', 0):.1f}%)
- 中性: {neutral} ({sentiment_result.get('neutral_percentage', 0):.1f}%)
"""

        # 添加关键主题
        key_themes = sentiment_result.get('key_themes', [])
        if key_themes:
            summary += "\n**关键主题**:\n"
            for theme in key_themes[:5]:  # 最多5个主题
                summary += f"- {theme}\n"

        # 添加代表性文章
        top_bullish = sentiment_result.get('top_bullish_articles', [])
        if top_bullish:
            summary += "\n**最积极文章**:\n"
            for i, item in enumerate(top_bullish[:2], 1):  # 最多2篇
                article = item.get('article', {})
                source = article.get('source', '未知来源')
                title = article.get('title', '(无标题)')
                summary += f"{i}. [{source}] {title}\n"

        top_bearish = sentiment_result.get('top_bearish_articles', [])
        if top_bearish:
            summary += "\n**最消极文章**:\n"
            for i, item in enumerate(top_bearish[:2], 1):  # 最多2篇
                article = item.get('article', {})
                source = article.get('source', '未知来源')
                title = article.get('title', '(无标题)')
                summary += f"{i}. [{source}] {title}\n"

        return summary.strip()

    def get_sentiment_emoji(self, sentiment: str) -> str:
        """
        获取情感倾向对应的表情符号

        Args:
            sentiment: 情感倾向 (bullish/bearish/neutral)

        Returns:
            表情符号
        """
        emoji_map = {
            'bullish': '📈',
            'bearish': '📉',
            'neutral': '➡️'
        }
        return emoji_map.get(sentiment, '➡️')
