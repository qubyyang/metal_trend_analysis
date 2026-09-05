"""
LLM 分析引擎模块
"""
import json
import re
from typing import Dict, List, Any, Optional
from openai import OpenAI
from loguru import logger

from ..utils.exceptions import LLMError, ValidationError, ConfigurationError
from ..utils.common import validate_config, with_retry


TREND_VALUES = ("看涨", "看跌", "中性")
RISK_VALUES = ("低", "中", "高")
CONFIDENCE_VALUES = ("低", "中", "高")

TREND_ALIASES = {
    "bullish": "看涨", "上涨": "看涨", "偏多": "看涨", "多头": "看涨",
    "bearish": "看跌", "下跌": "看跌", "偏空": "看跌", "空头": "看跌",
    "neutral": "中性", "震荡": "中性", "横盘": "中性", "观望": "中性",
}
RISK_ALIASES = {
    "low": "低", "较低": "低", "medium": "中", "中等": "中", "适中": "中",
    "high": "高", "较高": "高",
}

PATTERN_CN = {
    'doji': '十字星', 'hammer': '锤子线', 'shooting_star': '射击之星',
    'engulfing_bullish': '看涨吞噬', 'engulfing_bearish': '看跌吞噬',
    'morning_star': '早晨之星', 'evening_star': '黄昏之星',
    'three_white_soldiers': '三白兵', 'three_black_crows': '三黑鸦',
}

FACTOR_CN = {
    'ma_alignment': '均线排列', 'macd': 'MACD', 'rsi': 'RSI',
    'bollinger': '布林带', 'multi_period': '多周期', 'volume': '成交量',
}

MACD_CN = {
    'golden_cross': '金叉', 'death_cross': '死叉',
    'bullish': '多头动能', 'bearish': '空头动能', 'neutral': '中性',
}

NEWS_CAUSALITY_GUIDE = """**新闻因果分析要求**：

1. 判定每篇新闻的性质：
   - **原因驱动型**：事件本身推动价格（美联储利率决议、通胀数据、地缘冲突、央行购金）
   - **反应滞后型**：对已发生行情的事后解读（"金价创新高因避险情绪升温"）
   - **预期引导型**：尚未发生但影响预期（即将公布的数据、会议日程）

2. 严格区分「价格变动导致新闻」与「新闻推动价格」。
   反应滞后型新闻**不构成**方向证据，它只是价格的镜像，把它当依据会形成循环论证。

3. 对每条有效新闻给出驱动强度：强驱动 / 中等驱动 / 弱影响 / 无直接影响。

4. 若全部新闻均为反应滞后型，应明确说明"新闻无独立信息量"，并据此下调置信度。
"""

OUTPUT_CONTRACT = """## 四、输出要求

严格输出以下 JSON，不要包含任何额外文字、不要用 markdown 代码块包裹：

{
  "trend": "看涨 | 看跌 | 中性",
  "suggestion": "具体操作建议",
  "target_price": {"short_term": 数字, "medium_term": 数字},
  "risk_level": "低 | 中 | 高",
  "confidence": "低 | 中 | 高",
  "logic": "300字以内核心逻辑，须说明依据来自哪类证据",
  "key_points": ["要点1", "要点2", "要点3"],
  "evidence_quality": "说明本次判断依赖的证据类型及其可靠性，若主要依赖技术面须注明其无统计显著性"
}

字段约束：
- trend / risk_level / confidence 必须为上述枚举值之一，不得自创
- target_price 为数字，无法判断时填 null
- confidence 判定标准：有原因驱动型新闻或宏观事件支撑=中或高；
  仅有技术面或仅有反应滞后型新闻=低
"""


def _as_float(value: Any) -> Optional[float]:
    """宽松转 float，失败返回 None（LLM 输入常含 'N/A' 或字符串数字）。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if result != result else result  # 过滤 NaN

# 回测证伪结论，注入 prompt 以防止 LLM 把技术分数当独立证据背书。
# 依据：docs/因子调优验证报告.md
SIGNAL_CAVEAT = """
**关于上述技术信号的重要前提（必须遵守）**：

本系统的技术信号已经过完整回测与因子检验，结论如下：
- 242 条非重叠样本胜率 53.26%，z=+0.88 / p=0.3763，**与随机无统计显著差异**
- 择时期望收益 +0.111%/5日，**低于买入持有基准 +0.220%**
- 六因子 Spearman IC 全部 |IC| < 0.09（低于 0.03 噪声门槛者居多）
- 滚动 1 年 IC（20日持有）黄金均值 -0.269、白银 -0.246，多数窗口为负

因此你必须遵守：
1. **不得把技术评分本身当作看涨/看跌的独立依据**，它没有被证实的预测力
2. 技术指标只能用作"当前市场状态的描述"，不能用作"未来方向的证据"
3. 若你的结论主要依赖技术指标，置信度必须标为"低"
4. 优先从新闻、宏观事件、供需与跨品种关系中寻找有独立信息量的依据
5. 若确实缺乏有信息量的证据，应如实给出"中性 + 低置信度"，不要编造理由

诚实的"看不清"比自信的错误判断更有价值。
"""


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
        # 是否请求结构化 JSON 输出（部分自建网关不支持，失败后自动置 False）
        self.response_format_json = bool(config.get('response_format_json', True))

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

            # 调用 LLM。优先请求结构化 JSON 输出；模型/网关不支持时自动回退。
            create_kwargs = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是一位专业的贵金属市场分析师。你的首要职责是诚实评估证据强度，"
                            "而不是给出自信的判断。当证据不足时，明确说明不确定性。"
                            "请严格按要求的 JSON 格式输出，不要包含任何额外文字。"
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
            }

            response = None
            if self.response_format_json:
                try:
                    response = self.client.chat.completions.create(
                        response_format={"type": "json_object"}, **create_kwargs
                    )
                except Exception as e:
                    self.logger.warning(
                        f"json_object response_format unsupported, falling back: {e}"
                    )
                    self.response_format_json = False

            if response is None:
                response = self.client.chat.completions.create(**create_kwargs)

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
        """构建分析提示词。

        合并了此前两套构造器：完整版（新闻因果分析 + JSON 契约）此前是死代码，
        实际生效的是简化版。现统一为一套，并注入回测证伪结论（SIGNAL_CAVEAT）。
        """
        try:
            symbol_name = "黄金" if "XAU" in symbol.upper() else "白银"
            out: List[str] = [f"请分析 {symbol_name}（{symbol}）的市场情况。", ""]

            out.append("## 一、当前行情")
            price = _as_float(quote_data.get('price'))
            change = _as_float(quote_data.get('change'))
            change_pct = _as_float(quote_data.get('change_percent'))
            out.append(f"- 最新价格: ${price:.2f}" if price is not None else "- 最新价格: N/A")
            if change is not None and change_pct is not None:
                out.append(f"- 日涨跌: {change:+.2f} ({change_pct:+.2f}%)")
            low, high = _as_float(quote_data.get('low')), _as_float(quote_data.get('high'))
            if low is not None and high is not None:
                out.append(f"- 今日区间: ${low:.2f} - ${high:.2f}")
            out.append("")

            out.append("## 二、技术面（仅供描述现状，不作为方向证据）")
            trend = technical_data.get('trend', 'neutral')
            out.append(f"- 综合趋势: {TREND_ALIASES.get(trend, trend)}")

            rsi = _as_float(technical_data.get('rsi'))
            if rsi is not None:
                out.append(f"- RSI: {rsi:.1f}")
            if technical_data.get('macd_signal'):
                sig = technical_data['macd_signal']
                out.append(f"- MACD: {MACD_CN.get(sig, sig)}")

            for key, label in (('support_levels', '支撑位'), ('resistance_levels', '阻力位')):
                vals = [_as_float(v) for v in (technical_data.get(key) or [])[:3]]
                vals = [v for v in vals if v is not None]
                if vals:
                    out.append(f"- {label}: " + ", ".join(f"${v:.2f}" for v in vals))

            out.append(self._render_factor_detail(technical_data))

            patterns = technical_data.get('patterns') or {}
            pattern_lines = []
            for name, data in patterns.items():
                count = len(data) if isinstance(data, list) else int(data or 0)
                if count > 0:
                    pattern_lines.append(f"- {PATTERN_CN.get(name, name)}: {count}次")
            if pattern_lines:
                out.append("### K线形态")
                out.extend(pattern_lines)
            out.append("")

            out.append(SIGNAL_CAVEAT)

            out.append("## 三、基本面")
            out.append("### 3.1 相关新闻")
            if news_articles:
                out.append(f"共 {len(news_articles)} 篇，请分析其对价格的影响：")
                out.append("")
                for i, article in enumerate(news_articles[:10], 1):
                    title = (article.get('title') or '').strip()
                    if not title:
                        continue
                    source = article.get('source', '未知来源')
                    published = article.get('published', 'N/A')
                    out.append(f"{i}. [{source}] {title}")
                    out.append(f"   时间: {published}")
                    content = (article.get('content') or '').strip()
                    if content and len(content) < 200:
                        out.append(f"   摘要: {content}")
                out.append("")
                out.append(NEWS_CAUSALITY_GUIDE)
            else:
                out.append("暂无相关新闻。注意：缺少基本面信息时，")
                out.append("由于技术面已被证伪，你的置信度应当标为“低”。")
            out.append("")

            if gold_silver_ratio and symbol.upper() in ('XAUUSD', 'XAGUSD'):
                out.append("### 3.2 黄金白银比")
                out.append(f"- 当前: {gold_silver_ratio:.1f}（历史均值 60-70）")
                hint = ("白银相对强势，工业需求支撑" if gold_silver_ratio < 60
                        else "黄金相对强势，避险需求主导")
                out.append(f"- 启示: {hint}")
                out.append("")

            out.append(OUTPUT_CONTRACT)
            return "\n".join(out)

        except Exception as e:
            self.logger.error(f"Error building prompt: {e}")
            return (
                f"请分析 {symbol} 的市场情况。注意：本系统技术信号经回测无统计显著性，"
                f"不得作为方向证据。\n{OUTPUT_CONTRACT}"
            )

    @staticmethod
    def _render_factor_detail(technical_data: Dict[str, Any]) -> str:
        """渲染 SignalEngine 六因子明细，让 LLM 看到分数构成而非只有结论。"""
        detail = technical_data.get('signal_detail') or {}
        factors = detail.get('factors') or {}
        if not factors:
            return ""

        rows = ["", "### 因子评分明细（-1 ~ +1）"]
        for name, info in factors.items():
            if not isinstance(info, dict):
                continue
            if not info.get('valid', True):
                rows.append(f"- {FACTOR_CN.get(name, name)}: 数据不可用，已剔除")
                continue
            score = _as_float(info.get('score'))
            if score is None:
                continue
            reason = info.get('reason') or ''
            rows.append(f"- {FACTOR_CN.get(name, name)}: {score:+.2f} {reason}".rstrip())

        total = _as_float(detail.get('score'))
        eff_w = _as_float(detail.get('effective_weight'))
        if total is not None:
            line = f"- 加权总分: {total:+.1f} / 100"
            if eff_w is not None:
                line += f"（有效权重 {eff_w:.2f}）"
            rows.append(line)
        return "\n".join(rows)

    def _try_parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        尝试从 LLM 输出中提取 JSON 对象

        兼容三种常见形态：纯 JSON、```json 代码块包裹、JSON 前后带说明文字。

        Args:
            text: LLM 返回的原始文本

        Returns:
            解析成功返回字典，否则返回 None
        """
        if not text:
            return None

        # 先剥离 markdown 代码块围栏，否则 ```json ... ``` 会被 rfind('}') 截断失败
        fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
        candidates = [fence.group(1)] if fence else []
        candidates.append(text)

        for candidate in candidates:
            start = candidate.find('{')
            end = candidate.rfind('}') + 1
            if start < 0 or end <= start:
                continue
            try:
                data = json.loads(candidate[start:end])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data:
                return data
        return None

    def _normalize_enum(
        self, value: Any, allowed: tuple, aliases: Dict[str, str], default: str
    ) -> tuple:
        """把 LLM 返回的枚举值归一到白名单。

        Returns:
            (归一后的值, 是否发生了回退)
        """
        if not isinstance(value, str):
            return default, True
        text = value.strip()
        if text in allowed:
            return text, False
        lowered = text.lower()
        for key, mapped in aliases.items():
            if key in lowered:
                return mapped, False
        # 值本身含有合法枚举字样（如 "偏向看涨"）
        for item in allowed:
            if item in text:
                return item, False
        return default, True

    def _validate_analysis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """校验并归一 LLM 的结构化输出。

        契约优先于信任：字段缺失或类型错误时降级为保守值并记录 schema_warnings，
        而不是让脏数据流向报告与信号记录。
        """
        warnings: List[str] = []

        trend, fell_back = self._normalize_enum(
            data.get('trend'), TREND_VALUES, TREND_ALIASES, '中性')
        if fell_back:
            warnings.append(f"trend 非法或缺失，降级为中性（原值: {data.get('trend')!r}）")

        risk, fell_back = self._normalize_enum(
            data.get('risk_level'), RISK_VALUES, RISK_ALIASES, '中')
        if fell_back:
            warnings.append(f"risk_level 非法或缺失，降级为中（原值: {data.get('risk_level')!r}）")

        confidence, fell_back = self._normalize_enum(
            data.get('confidence'), CONFIDENCE_VALUES, RISK_ALIASES, '低')
        if fell_back:
            warnings.append(
                f"confidence 非法或缺失，降级为低（原值: {data.get('confidence')!r}）")

        # 目标价：非数字一律置 None，不猜
        targets = data.get('target_price')
        short_term = medium_term = None
        if isinstance(targets, dict):
            short_term = _as_float(targets.get('short_term'))
            medium_term = _as_float(targets.get('medium_term'))
        elif targets is not None:
            warnings.append("target_price 结构非法，已忽略")

        key_points = data.get('key_points')
        if isinstance(key_points, str):
            key_points = [key_points]
        elif not isinstance(key_points, list):
            key_points = []
            if data.get('key_points') is not None:
                warnings.append("key_points 结构非法，已置空")
        key_points = [str(p).strip() for p in key_points if str(p).strip()][:5]

        def _text(field: str, fallback: str) -> str:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value is not None:
                warnings.append(f"{field} 类型非法，已降级")
            return fallback

        result = {
            'trend': trend,
            'suggestion': _text('suggestion', '证据不足，建议观望'),
            'risk_level': risk,
            'confidence': confidence,
            'logic': _text('logic', '模型未提供核心逻辑'),
            'summary': _text('logic', '模型未提供核心逻辑')[:200],
            'target_price': {'short_term': short_term, 'medium_term': medium_term},
            'key_points': key_points,
            'evidence_quality': _text('evidence_quality', '未说明证据质量'),
            'schema_warnings': warnings,
        }

        # 纪律约束：技术面已被证伪，若模型未给出任何要点却报高置信度，强制下调
        if result['confidence'] == '高' and not key_points:
            result['confidence'] = '中'
            warnings.append("高置信度但无支撑要点，已下调为中")

        if warnings:
            self.logger.warning(
                f"LLM 输出契约校验发现 {len(warnings)} 处问题: {'; '.join(warnings)}")
        return result

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

            # 优先尝试解析 JSON，并强制通过契约校验
            json_data = self._try_parse_json(analysis_text)
            if json_data:
                return {
                    'analysis': self._validate_analysis(json_data),
                    'raw_text': analysis_text[:1000],
                    'parse_mode': 'json',
                    'error': None
                }

            # 回退：从自由文本中正则抽取结构化信息
            self.logger.warning("LLM 未返回合法 JSON，回退到文本抽取模式")
            analysis_data = {
                'trend': self._extract_trend(analysis_text),
                'summary': self._extract_summary(analysis_text),
                'suggestion': self._extract_suggestion(analysis_text),
                'risk_level': self._extract_risk_level(analysis_text),
                'key_levels': self._extract_key_levels(analysis_text),
                # 文本抽取本身不可靠，置信度一律标低
                'confidence': '低',
                'schema_warnings': ['未返回 JSON，结果由正则抽取，可靠性低'],
            }

            return {
                'analysis': analysis_data,
                'parse_mode': 'text',
                'raw_text': analysis_text[:1000],  # 限制长度
                'error': None
            }

        except Exception as e:
            self.logger.warning(f"Failed to parse LLM analysis: {e}")
            # 解析彻底失败：返回合法但保守的值，避免 'N/A' 污染下游信号记录
            return {
                'analysis': {
                    'summary': analysis_text[:500] if analysis_text else "分析解析失败",
                    'trend': '中性',
                    'suggestion': '解析失败，请查看原始文本',
                    'risk_level': '中',
                    'confidence': '低',
                    'schema_warnings': [f'解析失败: {e}'],
                },
                'parse_mode': 'failed',
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
