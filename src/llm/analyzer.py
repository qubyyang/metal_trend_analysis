"""
LLM 分析引擎模块
"""
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI


class LLMAnalyzer:
    """LLM 分析引擎"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 LLM 分析器

        Args:
            config: LLM 配置
        """
        self.provider = config.get('provider', 'openai')
        self.api_key = config.get('api_key', '')
        self.base_url = config.get('base_url', None)
        self.model = config.get('model', 'gpt-4o')
        self.temperature = config.get('temperature', 0.7)
        self.max_tokens = config.get('max_tokens', 2000)
        self.timeout = config.get('timeout', 60)

        # 初始化客户端
        if self.base_url:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                timeout=self.timeout
            )

    def analyze_market(
        self,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        news_articles: List[Dict[str, Any]],
        gold_silver_ratio: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        综合分析市场

        Args:
            symbol: 交易品种代码
            quote_data: 实时报价数据
            technical_data: 技术指标数据
            news_articles: 新闻列表
            gold_silver_ratio: 黄金白银比（可选）

        Returns:
            分析结果
        """
        # 构建提示词
        prompt = self._build_analysis_prompt(
            symbol,
            quote_data,
            technical_data,
            news_articles,
            gold_silver_ratio
        )

        # 调用 LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位专业的贵金属市场分析师，擅长技术分析和基本面分析。请基于提供的数据给出专业的市场分析。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )

            analysis_text = response.choices[0].message.content

            # 解析分析结果
            return self._parse_analysis(analysis_text)

        except Exception as e:
            return {
                'error': f"LLM 分析失败: {str(e)}",
                'analysis': None
            }

    def _build_analysis_prompt(
        self,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        news_articles: List[Dict[str, Any]],
        gold_silver_ratio: Optional[float] = None
    ) -> str:
        """
        构建分析提示词

        Args:
            symbol: 交易品种代码
            quote_data: 实时报价数据
            technical_data: 技术指标数据
            news_articles: 新闻列表
            gold_silver_ratio: 黄金白银比

        Returns:
            提示词文本
        """
        symbol_name = "黄金" if "XAU" in symbol else "白银"

        prompt = f"""请分析 {symbol_name} ({symbol}) 的市场情况。

## 一、当前行情数据
"""
        if quote_data:
            prompt += f"""
- 最新价格: ${quote_data.get('price', 'N/A')}
- 日涨跌: {quote_data.get('change', 'N/A')} ({quote_data.get('change_percent', 'N/A')}%)
- 最高价: ${quote_data.get('high', 'N/A')}
- 最低价: ${quote_data.get('low', 'N/A')}
"""

        prompt += """

## 二、技术面分析
"""

        if technical_data:
            # MA 趋势
            if 'ma_trend' in technical_data:
                prompt += "\n### 2.1 移动平均线\n"
                ma_trend = technical_data['ma_trend']
                ma_list = []
                for key, value in ma_trend.items():
                    if value:
                        ma_list.append(f"{key}=${value:.2f}")
                prompt += "- " + ", ".join(ma_list) + "\n"

                if technical_data.get('ma_alignment'):
                    prompt += "- 趋势判断: 多头排列，强势上涨\n"
                else:
                    prompt += "- 趋势判断: 震荡或下跌\n"

            # MACD
            if 'macd_signal' in technical_data:
                prompt += "\n### 2.2 MACD\n"
                macd_signal = technical_data['macd_signal']
                signal_text = {
                    'golden_cross': '金叉，买入信号',
                    'death_cross': '死叉，卖出信号',
                    'bullish': '多头，上涨动能',
                    'bearish': '空头，下跌动能'
                }.get(macd_signal, '中性')

                prompt += f"- 信号: {signal_text}\n"

            # RSI
            if 'rsi_signal' in technical_data:
                prompt += "\n### 2.3 RSI\n"
                rsi_signal = technical_data['rsi_signal']
                rsi_text = {
                    'overbought': '超买，注意回调风险',
                    'oversold': '超卖，存在反弹机会',
                    'normal': '正常区间'
                }.get(rsi_signal, '中性')

                prompt += f"- 状态: {rsi_text}\n"

            # 支撑阻力
            if 'support_levels' in technical_data or 'resistance_levels' in technical_data:
                prompt += "\n### 2.4 支撑阻力位\n"
                if 'support_levels' in technical_data:
                    supports = technical_data['support_levels']
                    if supports:
                        prompt += "- 支撑位: " + ", ".join([f"${s:.2f}" for s in supports[:2]]) + "\n"
                if 'resistance_levels' in technical_data:
                    resistances = technical_data['resistance_levels']
                    if resistances:
                        prompt += "- 阻力位: " + ", ".join([f"${r:.2f}" for r in resistances[:2]]) + "\n"

            # 综合趋势
            if 'trend' in technical_data:
                prompt += "\n### 2.5 综合趋势判断\n"
                trend = technical_data['trend']
                trend_text = {
                    'bullish': '看涨',
                    'bearish': '看跌',
                    'neutral': '中性'
                }.get(trend, '中性')

                prompt += f"- 趋势方向: {trend_text}\n"

            # K 线形态
            if 'patterns' in technical_data:
                prompt += "\n### 2.6 K 线形态\n"
                patterns = technical_data['patterns']
                if patterns:
                    for pattern_name, pattern_list in patterns.items():
                        if pattern_list:
                            pattern_cn = {
                                'doji': '十字星',
                                'hammer': '锤子线',
                                'shooting_star': '射击之星',
                                'engulfing_bullish': '看涨吞噬',
                                'engulfing_bearish': '看跌吞噬',
                                'morning_star': '早晨之星',
                                'evening_star': '黄昏之星',
                                'three_white_soldiers': '三白兵',
                                'three_black_crows': '三黑鸦'
                            }.get(pattern_name, pattern_name)

                            prompt += f"- {pattern_cn}: {len(pattern_list)}次\n"

        prompt += """

## 三、基本面分析

### 3.1 相关新闻与市场影响分析
"""
        if news_articles:
            prompt += f"\n\n共获取 {len(news_articles)} 篇相关新闻，请分析以下新闻对价格走势的影响：\n\n"
            for i, article in enumerate(news_articles[:10], 1):
                title = article.get('title', '')
                source = article.get('source', '')
                published = article.get('published', 'N/A')
                content = article.get('content', '')
                prompt += f"{i}. [{source}] {title}\n"
                prompt += f"   时间: {published}\n"
                if content and len(content) < 200:
                    prompt += f"   内容: {content}\n"
                prompt += "\n"

            prompt += """
**重要分析要求**：
1. 分析每篇新闻的性质：
   - 是"原因驱动型"新闻（如：美联储降息、通胀数据、地缘政治事件等导致价格变动）
   - 还是"反应滞后型"新闻（如：市场对已有价格事件的评论和解读）
   - 或是"预期引导型"新闻（如：即将公布的经济数据、央行会议等）

2. 识别因果关系：
   - 如果新闻是"原因驱动型"，说明该事件如何直接或间接影响贵金属价格
   - 如果新闻是"反应滞后型"，说明该新闻是对当前价格走势的解读，而非价格变动的原因
   - 如果新闻是"预期引导型"，说明该事件可能对价格产生的潜在影响

3. 综合判断：
   - 区分"价格变动导致新闻"和"新闻影响价格"两种不同情况
   - 给出新闻对当前价格走势的驱动程度（强驱动/中等驱动/弱影响/无直接影响）
   - 在操作建议中体现新闻因素的影响

"""
        else:
            prompt += "\n暂无相关新闻，主要依赖技术面分析\n"

        prompt += """

### 3.2 黄金白银比
"""
        if gold_silver_ratio:
            prompt += f"""
- 当前金银比: {gold_silver_ratio:.1f}
- 历史均值: 60-70
- 启示: {'白银相对黄金表现强势，工业需求支撑' if gold_silver_ratio < 60 else '黄金相对白银表现强势，避险需求主导'}
"""

        prompt += """

## 四、分析要求

请基于以上数据，给出以下分析：

1. **趋势方向**: 看涨/看跌/中性
2. **操作建议**: 具体的操作建议（如：回调至支撑位可考虑做多/阻力位附近可考虑减仓等，如受原因驱动型新闻影响，可适当调整仓位）
3. **目标价位**: 短期和中期的目标价位
4. **风险等级**: 低/中/高
5. **置信度**: 对判断的置信程度（高/中/低）
6. **核心逻辑**: 300字以内的核心分析逻辑，说明判断依据

请按照以下格式输出（使用JSON格式）：

```json
{
    "trend": "看涨/看跌/中性",
    "suggestion": "操作建议",
    "target_price": {
        "short_term": 0000.00,
        "medium_term": 0000.00
    },
    "risk_level": "低/中/高",
    "confidence": "高/中/低",
    "logic": "核心分析逻辑",
    "key_points": [
        "要点1",
        "要点2",
        "要点3"
    ]
}
```

注意：请务必输出纯JSON格式，不要包含其他文字说明。
"""

        return prompt

    def _parse_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """
        解析 LLM 分析结果

        Args:
            analysis_text: LLM 返回的文本

        Returns:
            解析后的结果
        """
        try:
            # 尝试提取 JSON
            # 查找 JSON 内容
            json_start = analysis_text.find('{')
            json_end = analysis_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = analysis_text[json_start:json_end]
                result = json.loads(json_str)

                return {
                    'analysis': result,
                    'raw_text': analysis_text
                }
            else:
                # 如果无法提取 JSON，返回原始文本
                return {
                    'analysis': None,
                    'raw_text': analysis_text
                }

        except json.JSONDecodeError:
            # JSON 解析失败，返回原始文本
            return {
                'analysis': None,
                'raw_text': analysis_text
            }

    def generate_report_summary(
        self,
        gold_analysis: Dict[str, Any],
        silver_analysis: Dict[str, Any]
    ) -> str:
        """
        生成综合报告摘要

        Args:
            gold_analysis: 黄金分析结果
            silver_analysis: 白银分析结果

        Returns:
            报告摘要
        """
        summary_lines = []

        summary_lines.append("## 综合市场分析\n")

        # 黄金分析
        if gold_analysis and gold_analysis.get('analysis'):
            gold_data = gold_analysis['analysis']
            summary_lines.append("### 黄金 (XAUUSD)")
            summary_lines.append(f"- 趋势: {gold_data.get('trend', 'N/A')}")
            summary_lines.append(f"- 建议: {gold_data.get('suggestion', 'N/A')}")
            summary_lines.append(f"- 风险: {gold_data.get('risk_level', 'N/A')}")
            summary_lines.append("")

        # 白银分析
        if silver_analysis and silver_analysis.get('analysis'):
            silver_data = silver_analysis['analysis']
            summary_lines.append("### 白银 (XAGUSD)")
            summary_lines.append(f"- 趋势: {silver_data.get('trend', 'N/A')}")
            summary_lines.append(f"- 建议: {silver_data.get('suggestion', 'N/A')}")
            summary_lines.append(f"- 风险: {silver_data.get('risk_level', 'N/A')}")
            summary_lines.append("")

        return '\n'.join(summary_lines)
