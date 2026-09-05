"""
LLM 分析引擎模块
"""
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from loguru import logger

from ..utils.exceptions import LLMError, ValidationError, ConfigurationError
from ..utils.common import validate_config, with_retry


class LLMAnalyzer:
    """LLM 分析引擎"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 LLM 分析器

        Args:
            config: LLM 配置

        Raises:
            ValidationError: 配置无效时抛出
            ConfigurationError: 配置错误时抛出
        """
        self.logger = logger.bind(name=self.__class__.__name__)

        # 验证配置
        required_fields = ['api_key']
        validate_config(config, required_fields, "LLM config")

        self.provider = config.get('provider', 'openai')
        self.api_key = config.get('api_key', '')
        self.base_url = config.get('base_url', None)
        self.model = config.get('model', 'gpt-4o')
        self.temperature = max(0.0, min(2.0, config.get('temperature', 0.7)))  # Clamp between 0-2
        self.max_tokens = max(100, min(8000, config.get('max_tokens', 2000)))  # Reasonable limits
        self.timeout = max(10, config.get('timeout', 60))  # Minimum 10 seconds

        # 验证API密钥
        if not self.api_key or not isinstance(self.api_key, str):
            raise ValidationError("LLM API key is required and must be a string")

        # 初始化客户端
        try:
            client_kwargs = {
                'api_key': self.api_key,
                'timeout': self.timeout
            }

            if self.base_url:
                if not self.base_url.startswith(('http://', 'https://')):
                    raise ValidationError("LLM base URL must start with http:// or https://")
                client_kwargs['base_url'] = self.base_url

            self.client = OpenAI(**client_kwargs)
            self.logger.info(f"LLM client initialized: provider={self.provider}, model={self.model}")

        except Exception as e:
            raise ConfigurationError(f"Failed to initialize LLM client: {e}")

    @with_retry(max_attempts=2, exceptions=(LLMError,))
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

        Raises:
            ValidationError: 输入参数无效
            LLMError: LLM调用失败
        """
        try:
            # 验证输入参数
            if not symbol or not isinstance(symbol, str):
                raise ValidationError("Symbol must be a non-empty string")

            if not quote_data or not isinstance(quote_data, dict):
                raise ValidationError("Quote data must be a non-empty dictionary")

            if not technical_data or not isinstance(technical_data, dict):
                raise ValidationError("Technical data must be a non-empty dictionary")

            # 构建提示词
            prompt = self._build_analysis_prompt(
                symbol,
                quote_data,
                technical_data,
                news_articles or [],
                gold_silver_ratio
            )

            self.logger.debug(f"Analyzing market for {symbol}")

            # 调用 LLM
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

            if not analysis_text:
                raise LLMError("LLM returned empty response")

            # 解析分析结果
            result = self._parse_analysis(analysis_text)
            self.logger.info(f"LLM analysis completed for {symbol}")
            return result

        except ValidationError:
            raise
        except Exception as e:
            error_msg = f"LLM 分析失败: {str(e)}"
            self.logger.error(error_msg)
            raise LLMError(error_msg)

    def _build_analysis_prompt(
        self,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        news_articles: List[Dict[str, Any]],
        gold_silver_ratio: Optional[float]
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
            格式化的提示词字符串
        """
        try:
            lines = [f"请分析 {symbol} 的市场情况："]
            lines.append("")

            # 价格信息
            lines.append("## 价格信息")
            price = quote_data.get('price', 0)
            change = quote_data.get('change', 0)
            change_pct = quote_data.get('change_percent', 0)

            lines.append(f"- 当前价格: ${price:.2f}")
            lines.append(f"- 涨跌: {change:+.2f} ({change_pct:+.2f}%)")
            lines.append(f"- 今日区间: ${quote_data.get('low', 0):.2f} - ${quote_data.get('high', 0):.2f}")
            lines.append("")

            # 技术指标
            lines.append("## 技术指标")
            trend = technical_data.get('trend', 'neutral')
            lines.append(f"- 整体趋势: {trend}")

            support_levels = technical_data.get('support_levels', [])
            resistance_levels = technical_data.get('resistance_levels', [])

            if support_levels:
                support_str = ", ".join([f"${s:.2f}" for s in support_levels[:3] if isinstance(s, (int, float))])
                if support_str:
                    lines.append(f"- 支撑位: {support_str}")

            if resistance_levels:
                resistance_str = ", ".join([f"${r:.2f}" for r in resistance_levels[:3] if isinstance(r, (int, float))])
                if resistance_str:
                    lines.append(f"- 阻力位: {resistance_str}")

            # 添加其他技术指标
            if technical_data.get('rsi') is not None:
                rsi = technical_data['rsi']
                lines.append(f"- RSI: {rsi:.1f}")

            if technical_data.get('macd_signal'):
                macd_signal = technical_data['macd_signal']
                lines.append(f"- MACD信号: {macd_signal}")

            lines.append("")

            # K线形态
            patterns = technical_data.get('patterns', {})
            if patterns:
                pattern_count = sum(len(v) if isinstance(v, list) else int(v or 0) for v in patterns.values())
                if pattern_count > 0:
                    lines.append("## K线形态")
                    for pattern_name, pattern_data in patterns.items():
                        count = len(pattern_data) if isinstance(pattern_data, list) else int(pattern_data or 0)
                        if count > 0:
                            lines.append(f"- {pattern_name}: {count}个")
                    lines.append("")

            # 新闻信息
            if news_articles:
                lines.append("## 相关新闻")
                for i, article in enumerate(news_articles[:3]):  # 只显示前3条
                    title = article.get('title', '').strip()
                    if title:
                        lines.append(f"- {title}")
                if len(news_articles) > 3:
                    lines.append(f"- ...还有{len(news_articles) - 3}条相关新闻")
                lines.append("")

            # 黄金白银比
            if gold_silver_ratio and symbol.upper() in ['XAUUSD', 'XAGUSD']:
                lines.append("## 黄金白银比")
                lines.append(f"- 当前比值: {gold_silver_ratio:.1f}")
                lines.append(f"- 历史均值: 60-70")
                lines.append("")

            # 分析要求
            lines.append("## 请提供以下分析:")
            lines.append("1. 短期趋势判断（看涨/看跌/震荡）")
            lines.append("2. 关键技术位分析")
            lines.append("3. 风险评估（高/中/低）")
            lines.append("4. 操作建议")
            lines.append("5. 主要影响因素")
            lines.append("")
            lines.append("请用结构化的方式回答，便于解析。")

            return "\n".join(lines)

        except Exception as e:
            self.logger.error(f"Error building prompt: {e}")
            return f"请分析 {symbol} 的市场情况，包括趋势判断、技术分析和操作建议。"

    def _try_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        尝试从 LLM 输出中提取 JSON 对象

        Args:
            text: LLM 返回的原始文本

        Returns:
            解析成功返回字典，否则返回 None
        """
        start = text.find('{')
        end = text.rfind('}') + 1
        if start < 0 or end <= start:
            return None

        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            return None

        return data if isinstance(data, dict) and data else None

    def _parse_analysis(self, analysis_text: str) -> Dict[str, Any]:
        """
        解析LLM分析结果

        Args:
            analysis_text: LLM返回的分析文本

        Returns:
            结构化的分析结果
        """
        try:
            if not analysis_text or not isinstance(analysis_text, str):
                raise ValueError("Analysis text is empty or invalid")

            # 优先尝试解析 JSON（部分提示词要求模型返回 JSON）
            json_data = self._try_parse_json(analysis_text)
            if json_data:
                return {
                    'analysis': json_data,
                    'raw_text': analysis_text[:1000],
                    'error': None
                }

            # 回退：从自由文本中正则抽取结构化信息
            analysis_data = {
                'trend': self._extract_trend(analysis_text),
                'summary': self._extract_summary(analysis_text),
                'suggestion': self._extract_suggestion(analysis_text),
                'risk_level': self._extract_risk_level(analysis_text),
                'key_levels': self._extract_key_levels(analysis_text)
            }

            return {
                'analysis': analysis_data,
                'raw_text': analysis_text[:1000],  # 限制长度
                'error': None
            }

        except Exception as e:
            self.logger.warning(f"Failed to parse LLM analysis: {e}")
            # 如果解析失败，返回原始文本
            return {
                'analysis': {
                    'summary': analysis_text[:500] if analysis_text else "分析解析失败",
                    'trend': 'N/A',
                    'suggestion': '请查看详细分析文本',
                    'risk_level': 'N/A'
                },
                'raw_text': analysis_text[:1000] if analysis_text else "",
                'error': f"解析错误: {str(e)}"
            }

    def _extract_trend(self, text: str) -> str:
        """从分析文本中提取趋势判断"""
        try:
            text_lower = text.lower()
            if any(word in text_lower for word in ['看涨', 'bullish', '上涨', '上升']):
                return '看涨'
            elif any(word in text_lower for word in ['看跌', 'bearish', '下跌', '下降']):
                return '看跌'
            elif any(word in text_lower for word in ['震荡', 'sideways', '横盘', '中性']):
                return '震荡'
            else:
                return '中性'
        except Exception:
            return '中性'

    def _extract_summary(self, text: str) -> str:
        """提取分析摘要"""
        try:
            # 尝试提取第一段作为摘要
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if lines:
                # 找到第一个非标题行作为摘要
                for line in lines:
                    if not line.startswith('#') and not line.startswith('##') and len(line) > 10:
                        return line[:200]
            return text[:200] if text else "无摘要"
        except Exception:
            return text[:200] if text else "无摘要"

    def _extract_suggestion(self, text: str) -> str:
        """提取操作建议"""
        try:
            # 寻找包含"建议"、"操作"等关键词的段落
            lines = text.split('\n')
            suggestion_lines = []

            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ['建议', '操作', 'suggestion', 'recommend']):
                    # 收集这一行和后续相关行
                    suggestion_lines.append(line.strip())
                    for j in range(i + 1, min(i + 3, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith('#'):
                            suggestion_lines.append(next_line)

            if suggestion_lines:
                return ' '.join(suggestion_lines)[:300]
            else:
                return "请参考详细分析"
        except Exception:
            return "请参考详细分析"

    def _extract_risk_level(self, text: str) -> str:
        """提取风险等级"""
        try:
            text_lower = text.lower()
            if any(word in text_lower for word in ['高风险', 'high risk', '风险较高']):
                return '高'
            elif any(word in text_lower for word in ['低风险', 'low risk', '风险较低']):
                return '低'
            elif any(word in text_lower for word in ['中等风险', 'medium risk', '适中']):
                return '中'
            else:
                return '中'
        except Exception:
            return '中'

    def _extract_key_levels(self, text: str) -> str:
        """提取关键点位信息"""
        try:
            # 寻找价格相关的数字
            import re
            price_pattern = r'\$?\s*(\d+\.?\d*)'
            matches = re.findall(price_pattern, text)
            if matches:
                # 提取前几个价格点位
                levels = [f"${match}" for match in matches[:3]]
                return ", ".join(levels)
            else:
                return "见技术分析"
        except Exception:
            return "见技术分析"

    def _build_prompt(
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
