"""
钉钉通知推送模块

功能：
1. 发送文本消息到钉钉群
2. 发送Markdown格式消息
3. 支持长消息自动分批发送
4. 针对贵金属行情优化的消息格式
"""

import os
import time
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base import BaseNotifier
from ..utils.exceptions import NotificationError, ValidationError, NetworkError


class DingTalkNotifier(BaseNotifier):
    """钉钉通知推送器"""

    # 钉钉消息长度限制
    MAX_MARKDOWN_BYTES = 50000  # Markdown消息限制约20KB

    def __init__(self, webhook_url: str = None, timeout: int = 30, **kwargs):
        """
        初始化钉钉推送器

        Args:
            webhook_url: 钉钉机器人 Webhook URL，不传则从环境变量读取
            timeout: 请求超时时间
            **kwargs: 其他配置参数
        """
        self.webhook_url = webhook_url or os.getenv('DINGTALK_WEBHOOK_URL', '')
        super().__init__(timeout=timeout, webhook_url=self.webhook_url, **kwargs)

    def _validate_config(self, **kwargs) -> None:
        """验证钉钉配置"""
        webhook_url = kwargs.get('webhook_url', '')
        if webhook_url and not webhook_url.startswith('https://'):
            raise ValidationError("DingTalk webhook URL must be HTTPS")

        if not webhook_url:
            self.logger.warning("钉钉 Webhook URL 未配置，推送功能将不可用")

    def is_available(self) -> bool:
        """检查钉钉推送是否可用"""
        return bool(self.webhook_url)

    def _send_message(self, message: str, **kwargs) -> bool:
        """
        发送原始消息到钉钉

        Args:
            message: 消息内容
            **kwargs: 额外参数

        Returns:
            是否发送成功

        Raises:
            NotificationError: 发送失败时抛出
        """
        payload = {
            "msgtype": "text",
            "text": {
                "content": self._truncate_message(message, self.MAX_MARKDOWN_BYTES)
            }
        }

        return self._send_request(payload)

    def send_markdown(self, title: str, text: str) -> bool:
        """
        发送 Markdown 格式消息

        Args:
            title: 消息标题
            text: Markdown格式的内容

        Returns:
            是否发送成功
        """
        if not self.is_available():
            self.logger.warning("钉钉 Webhook 未配置，跳过推送")
            return False

        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": self._truncate_message(text, self.MAX_MARKDOWN_BYTES)
                }
            }

            return self._send_request(payload)

        except Exception as e:
            self.logger.error(f"Error sending markdown message: {e}")
            return False

    def send_market_report(
        self,
        symbol_name: str,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        patterns: Dict[str, int] = None,
        llm_analysis: Dict[str, Any] = None
    ) -> bool:
        """
        发送市场分析报告（贵金属专用格式）

        Args:
            symbol_name: 品种名称 (如 "国际现货黄金")
            symbol: 品种代码 (如 "XAUUSD")
            quote_data: 实时报价数据
            technical_data: 技术分析数据
            patterns: K线形态统计
            llm_analysis: LLM 分析结果

        Returns:
            是否发送成功
        """
        # 构建钉钉 Markdown 内容
        content = self._build_market_report_content(
            symbol_name, symbol, quote_data, technical_data, patterns, llm_analysis
        )

        # 生成标题
        price = quote_data.get('price', 0) if quote_data else 0
        change_pct = quote_data.get('change_percent', 0) if quote_data else 0
        trend_icon = "📈" if change_pct > 0 else ("📉" if change_pct < 0 else "➡")
        title = f"{trend_icon} {symbol_name} ${price:.2f} ({change_pct:+.2f}%)"

        return self.send_markdown(title, content)

    def send_daily_summary(
        self,
        reports: List[Dict[str, Any]],
        gold_silver_ratio: float = None
    ) -> bool:
        """
        发送每日汇总报告

        Args:
            reports: 多个品种的分析报告列表
            gold_silver_ratio: 黄金白银比

        Returns:
            是否发送成功
        """
        content = self._build_daily_summary_content(reports, gold_silver_ratio)
        title = f"📊 贵金属每日分析汇总 ({datetime.now().strftime('%Y-%m-%d')})"

        return self.send_markdown(title, content)

    def _get_card_footer(self, data_source: str = "Stooq") -> str:
        """生成消息的页脚"""
        return f"{self.DISCLAIMER}\n\n更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据来源: {data_source}"

    def _build_market_report_content(
        self,
        symbol_name: str,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        patterns: Dict[str, int] = None,
        llm_analysis: Dict[str, Any] = None
    ) -> str:
        """构建市场报告内容"""
        lines = []

        # === 行情概览 ===
        lines.append("## 📈 实时行情")

        if quote_data:
            price = quote_data.get('price', 0)
            change = quote_data.get('change', 0)
            change_pct = quote_data.get('change_percent', 0)
            high = quote_data.get('high', 0)
            low = quote_data.get('low', 0)
            open_price = quote_data.get('open', 0)

            # 涨跌颜色标识（使用钉钉支持的符号）
            if change > 0:
                trend_color = "🔴"
                trend_text = "上涨"
            elif change < 0:
                trend_color = "🟢"
                trend_text = "下跌"
            else:
                trend_color = "⚪"
                trend_text = "持平"

            lines.append(f"- 最新价: **${price:.2f}**")
            lines.append(f"- 涨跌额: {trend_color} {change:+.2f}")
            lines.append(f"- 涨跌幅: {trend_color} {change_pct:+.2f}%")
            lines.append(f"- 今日区间: ${low:.2f} ~ ${high:.2f}")
            lines.append(f"- 开盘价: ${open_price:.2f}")
        else:
            lines.append("- 暂无行情数据")

        lines.append("")

        # === 技术指标 ===
        if technical_data:
            lines.append("## 📊 技术指标")

            # 趋势判断
            trend = technical_data.get('trend', 'neutral')
            trend_text = {"bullish": "📈 看涨", "bearish": "📉 看跌", "neutral": "➡️ 震荡"}.get(trend, "➡️ 震荡")
            lines.append(f"- 趋势判断: {trend_text}")

            # 支撑阻力位
            support = technical_data.get('support_levels', [])
            resistance = technical_data.get('resistance_levels', [])

            if support:
                support_str = ", ".join([f"${s:.2f}" if isinstance(s, (int, float)) else str(s) for s in support[:2]])
                lines.append(f"- 支撑位: {support_str}")

            if resistance:
                resistance_str = ", ".join([f"${r:.2f}" if isinstance(r, (int, float)) else str(r) for r in resistance[:2]])
                lines.append(f"- 阻力位: {resistance_str}")

            # RSI
            if 'rsi' in technical_data and technical_data['rsi'] is not None:
                rsi = technical_data['rsi']
                rsi_status = "超买" if rsi > 70 else ("超卖" if rsi < 30 else "正常")
                lines.append(f"- RSI(14): {rsi:.1f} ({rsi_status})")

            # MACD
            if 'macd_signal' in technical_data:
                macd_signal = technical_data['macd_signal']
                macd_text = "金叉 📈" if macd_signal == 'bullish' else ("死叉 📉" if macd_signal == 'bearish' else "震荡 ➡️")
                lines.append(f"- MACD信号: {macd_text}")

            lines.append("")

        # === K线形态 ===
        if patterns:
            # 形态名称中英文映射
            pattern_names = {
                'doji': '十字星',
                'hammer': '锤子线',
                'shooting_star': '射击之星',
                'engulfing_bullish': '看涨吞噬',
                'engulfing_bearish': '看跌吞噬',
                'morning_star': '启明星',
                'evening_star': '黄昏之星',
                'three_white_soldiers': '三白兵',
                'three_black_crows': '三黑鸦'
            }

            has_patterns = False
            pattern_lines = []
            for pattern_key, pattern_data in patterns.items():
                # pattern_data 可能是列表或数字
                if isinstance(pattern_data, list):
                    count = len(pattern_data)
                elif isinstance(pattern_data, (int, float)):
                    count = int(pattern_data)
                else:
                    count = 0

                if count > 0:
                    has_patterns = True
                    name = pattern_names.get(pattern_key, pattern_key)
                    pattern_lines.append(f"- {name}: {count}次")

            if has_patterns:
                lines.append("## 🕯️ K线形态识别")
                lines.extend(pattern_lines)
                lines.append("")

        # === LLM 分析 ===
        if llm_analysis:
            # 处理不同格式的 LLM 分析结果
            analysis_content = llm_analysis.get('analysis', {})

            # 如果是嵌套字典格式
            if isinstance(analysis_content, dict):
                lines.append("## 🤖 AI 智能分析")

                # 趋势分析
                if analysis_content.get('trend'):
                    trend_icon = "📈" if analysis_content['trend'] in ['看涨', 'bullish'] else (
                        "📉" if analysis_content['trend'] in ['看跌', 'bearish'] else "➡️"
                    )
                    lines.append(f"- 趋势判断: {trend_icon} {analysis_content['trend']}")

                # 分析概要
                if analysis_content.get('summary'):
                    lines.append(f"- 分析概要: {analysis_content['summary'][:200]}")

                # 关键点位
                if analysis_content.get('key_levels'):
                    lines.append(f"- 关键点位: {analysis_content['key_levels']}")

                # 风险等级
                if analysis_content.get('risk_level'):
                    risk_icon = {"低": "🟢", "中": "🟡", "高": "🔴"}.get(analysis_content['risk_level'], "⚪")
                    lines.append(f"- 风险等级: {risk_icon} {analysis_content['risk_level']}")

                lines.append("")

                # 操作建议（单独展示，更醒目）
                if analysis_content.get('suggestion'):
                    suggestion = analysis_content['suggestion']
                    if len(suggestion) > 300:
                        suggestion = suggestion[:300] + "..."
                    lines.append("## 💡 操作建议")
                    lines.append(suggestion)
                    lines.append("")

            # 如果是字符串格式
            elif isinstance(analysis_content, str) and analysis_content:
                lines.append("## 🤖 AI 智能分析")
                if len(analysis_content) > 500:
                    analysis_content = analysis_content[:500] + "..."
                lines.append(analysis_content)
                lines.append("")

            # 兼容旧格式的 recommendation
            elif llm_analysis.get('recommendation'):
                lines.append(f"## 💡 操作建议")
                lines.append(llm_analysis['recommendation'])
                lines.append("")

        # 添加页脚
        footer = self._get_card_footer()
        lines.append("")
        lines.append("---")
        lines.append(footer)

        return "\n".join(lines)

    def _build_daily_summary_content(
        self,
        reports: List[Dict[str, Any]],
        gold_silver_ratio: float = None
    ) -> str:
        """构建每日汇总内容"""
        lines = []

        # 黄金白银比
        if gold_silver_ratio:
            lines.append("## ⚖️ 黄金白银比")
            ratio_status = "白银相对强势" if gold_silver_ratio < 60 else ("黄金相对强势" if gold_silver_ratio > 80 else "正常区间")
            lines.append(f"- 当前比值: **{gold_silver_ratio:.1f}**")
            lines.append(f"- 历史均值: 60-70")
            lines.append(f"- 研判: {ratio_status}")
            lines.append("")
            lines.append("---")
            lines.append("")

        # 各品种概览
        for report in reports:
            symbol_name = report.get('symbol_name', '')
            symbol = report.get('symbol', '')
            quote = report.get('quote_data', {})
            technical = report.get('technical_data', {})
            price = quote.get('price', 0)
            change_pct = quote.get('change_percent', 0)
            trend = technical.get('trend', 'neutral')
            trend_icon = "📈" if change_pct > 0 else ("📉" if change_pct < 0 else "➡️")
            trend_text = {"bullish": "看涨", "bearish": "看跌", "neutral": "震荡"}.get(trend, "震荡")

            lines.append(f"## {trend_icon} {symbol_name} ({symbol})")
            lines.append(f"- 价格: ${price:.2f} ({change_pct:+.2f}%)")
            lines.append(f"- 趋势: {trend_text}")

            # 支撑阻力位简要
            support = technical.get('support_levels', [])
            resistance = technical.get('resistance_levels', [])

            if support:
                lines.append(f"- 支撑: ${support[0]:.2f}" if isinstance(support[0], (int, float)) else f"- 支撑: {support[0]}")
            if resistance:
                lines.append(f"- 阻力: ${resistance[0]:.2f}" if isinstance(resistance[0], (int, float)) else f"- 阻力: {resistance[0]}")

            lines.append("")

        # 添加页脚
        footer = self._get_card_footer()
        lines.append("---")
        lines.append(footer)

        return "\n".join(lines)

    def _send_request(self, payload: Dict[str, Any]) -> bool:
        """发送请求到钉钉 Webhook"""
        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                result = response.json()
                errcode = result.get('errcode', -1)
                errmsg = result.get('errmsg', '未知错误')

                if errcode == 0:
                    logger.info("钉钉消息发送成功")
                    return True
                else:
                    logger.error(f"钉钉返回错误 [code={errcode}]: {errmsg}")
                    return False
            else:
                logger.error(f"钉钉请求失败: HTTP {response.status_code}")
                logger.debug(f"响应内容: {response.text}")
                return False

        except requests.exceptions.Timeout:
            logger.error("钉钉请求超时")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"钉钉请求异常: {e}")
            return False

    def send_chunked(
        self,
        title: str,
        content: str,
        max_bytes: int = None
    ) -> bool:
        """
        分批发送长消息

        Args:
            title: 消息标题
            content: 完整内容
            max_bytes: 单条消息最大字节数

        Returns:
            是否全部发送成功
        """
        if max_bytes is None:
            max_bytes = self.MAX_MARKDOWN_BYTES

        content_bytes = len(content.encode('utf-8'))

        if content_bytes <= max_bytes:
            return self.send_markdown(title, content)

        # 按段落分割
        chunks = self._split_content(content, max_bytes)
        total_chunks = len(chunks)

        logger.info(f"钉钉消息分批发送：共 {total_chunks} 批")
        success_count = 0
        for i, chunk in enumerate(chunks):
            chunk_title = f"{title} ({i + 1}/{total_chunks})"
            if self.send_markdown(chunk_title, chunk):
                success_count += 1
            else:
                logger.error(f"钉钉第 {i + 1}/{total_chunks} 批发送失败")
            # 批次间间隔，避免触发限流
            if i < total_chunks - 1:
                time.sleep(1)

        return success_count == total_chunks

    def _split_content(self, content: str, max_bytes: int) -> List[str]:
        """按字节大小分割内容"""
        chunks = []
        current_chunk = ""

        # 按段落或分隔线分割
        if "\n---\n" in content:
            sections = content.split("\n---\n")
            separator = "\n---\n"
        elif "\n\n" in content:
            sections = content.split("\n\n")
            separator = "\n\n"
        else:
            sections = content.split("\n")
            separator = "\n"

        for section in sections:
            test_chunk = current_chunk + separator + section if current_chunk else section
            test_bytes = len(test_chunk.encode('utf-8'))

            if test_bytes > max_bytes and current_chunk:
                chunks.append(current_chunk)
                current_chunk = section
            else:
                current_chunk = test_chunk

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
