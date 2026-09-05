"""
报告生成器模块
"""
import json
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path


class ReportGenerator:
    """报告生成器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化报告生成器

        Args:
            config: 报告配置
        """
        self.output_dir = Path(config.get('output_dir', 'output/reports'))
        self.format = config.get('format', 'markdown')
        self.include_charts = config.get('include_charts', False)

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_markdown_report(
        self,
        symbol: str,
        symbol_name: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        news_articles: List[Dict[str, Any]],
        llm_analysis: Dict[str, Any],
        gold_silver_ratio: float = None
    ) -> str:
        """
        生成 Markdown 格式报告

        Args:
            symbol: 交易品种代码
            symbol_name: 交易品种名称
            quote_data: 实时报价数据
            technical_data: 技术指标数据
            news_articles: 新闻列表
            llm_analysis: LLM 分析结果
            gold_silver_ratio: 黄金白银比

        Returns:
            报告内容
        """
        report_lines = []

        # 标题
        report_lines.append(f"# {symbol_name}市场分析报告")
        report_lines.append("")
        report_lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"**交易品种**: {symbol}")
        report_lines.append("")
        report_lines.append("---")
        report_lines.append("")

        # 一、当前行情
        report_lines.append("## 一、当前行情")
        report_lines.append("")

        if quote_data:
            def _fmt(key: str, digits: int = 2) -> str:
                """格式化数值，缺失或非数值时返回 N/A"""
                value = quote_data.get(key)
                if value is None:
                    return 'N/A'
                try:
                    return f"{float(value):,.{digits}f}"
                except (TypeError, ValueError):
                    return 'N/A'

            change = quote_data.get('change')
            # 涨跌前置符号，便于快速识别方向
            sign = '+' if isinstance(change, (int, float)) and change > 0 else ''

            report_lines.append("### 1.1 实时报价")
            report_lines.append("")
            report_lines.append(f"- 最新价格: ${_fmt('price')}")
            report_lines.append(
                f"- 日涨跌: {sign}{_fmt('change')} ({sign}{_fmt('change_percent')}%)"
            )
            report_lines.append(f"- 最高价: ${_fmt('high')}")
            report_lines.append(f"- 最低价: ${_fmt('low')}")
            report_lines.append(f"- 开盘价: ${_fmt('open')}")
            if quote_data.get('source'):
                report_lines.append(f"- 数据来源: {quote_data['source']}")
            report_lines.append("")

        # 二、技术面分析
        report_lines.append("## 二、技术面分析")
        report_lines.append("")

        if technical_data:
            # 趋势指标
            report_lines.append("### 2.1 趋势指标")
            report_lines.append("")

            # MA
            if 'ma_trend' in technical_data:
                report_lines.append("#### 移动平均线")
                ma_trend = technical_data['ma_trend']
                ma_list = []
                for key, value in ma_trend.items():
                    if value is not None:
                        ma_list.append(f"MA{key.split('MA')[-1]}={value:.2f}")

                if ma_list:
                    report_lines.append(f"- MA系统: {', '.join(ma_list)}")

                    if technical_data.get('ma_alignment'):
                        report_lines.append("  - 趋势判断: 多头排列，强势上涨")
                    else:
                        report_lines.append("  - 趋势判断: 震荡或下跌")
                report_lines.append("")

            # MACD
            if 'macd_signal' in technical_data:
                report_lines.append("#### MACD")
                macd_signal = technical_data['macd_signal']
                signal_text = {
                    'golden_cross': '金叉，零轴上方，多头动能延续',
                    'death_cross': '死叉，零轴下方，空头动能延续',
                    'bullish': '多头，零轴上方',
                    'bearish': '空头，零轴下方'
                }.get(macd_signal, '中性')

                report_lines.append(f"- 信号: {signal_text}")
                report_lines.append("")

            # RSI
            if 'rsi_signal' in technical_data:
                report_lines.append("### 2.2 震荡指标")
                report_lines.append("")

                report_lines.append("#### RSI")
                rsi_signal = technical_data['rsi_signal']
                rsi_text = {
                    'overbought': '超买，注意回调风险',
                    'oversold': '超卖，存在反弹机会',
                    'normal': '正常区间'
                }.get(rsi_signal, '中性')

                report_lines.append(f"- RSI(14): {rsi_text}")
                report_lines.append("")

            # 支撑阻力
            if 'support_levels' in technical_data or 'resistance_levels' in technical_data:
                report_lines.append("### 2.3 支撑阻力")
                report_lines.append("")

                if 'support_levels' in technical_data:
                    supports = technical_data['support_levels']
                    if supports:
                        report_lines.append("- 第一支撑: ${:.2f}".format(supports[0]))
                        if len(supports) > 1:
                            report_lines.append("- 第二支撑: ${:.2f}".format(supports[1]))

                if 'resistance_levels' in technical_data:
                    resistances = technical_data['resistance_levels']
                    if resistances:
                        report_lines.append("- 第一阻力: ${:.2f}".format(resistances[0]))
                        if len(resistances) > 1:
                            report_lines.append("- 第二阻力: ${:.2f}".format(resistances[1]))

                report_lines.append("")

            # K 线形态
            if 'patterns' in technical_data:
                report_lines.append("### 2.4 K 线形态")
                report_lines.append("")

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

                            report_lines.append(f"- {pattern_cn}: {len(pattern_list)}次")

                    report_lines.append("")
                else:
                    report_lines.append("近期未检测到明显的 K 线形态")
                    report_lines.append("")

            # 综合趋势
            if 'trend' in technical_data:
                report_lines.append("### 2.5 技术面综合判断")
                report_lines.append("")

                trend = technical_data['trend']
                trend_text = {
                    'bullish': '看涨',
                    'bearish': '看跌',
                    'neutral': '中性'
                }.get(trend, '中性')

                report_lines.append(f"- 趋势方向: {trend_text}")
                report_lines.append("")

        # 三、基本面分析
        report_lines.append("## 三、基本面分析")
        report_lines.append("")

        # 黄金白银比
        if gold_silver_ratio:
            report_lines.append("### 3.1 黄金白银比")
            report_lines.append("")
            report_lines.append(f"- 当前金银比: {gold_silver_ratio:.1f}")
            report_lines.append("- 历史均值: 60-70")

            if gold_silver_ratio < 60:
                report_lines.append("- 启示: 白银相对黄金表现强势，工业需求支撑")
            elif gold_silver_ratio > 70:
                report_lines.append("- 启示: 黄金相对白银表现强势，避险需求主导")
            else:
                report_lines.append("- 启示: 金银比在正常范围内")

            report_lines.append("")

        # 相关新闻
        report_lines.append("### 3.2 相关新闻")
        report_lines.append("")

        # 新闻情感分析
        if 'news_sentiment' in technical_data:
            from src.analyzers.news_sentiment import NewsSentimentAnalyzer
            sentiment_analyzer = NewsSentimentAnalyzer()
            sentiment_summary = sentiment_analyzer.get_sentiment_summary(technical_data['news_sentiment'])
            report_lines.append(sentiment_summary)
            report_lines.append("")
            report_lines.append("**最新新闻**:")
            report_lines.append("")

        if news_articles:
            for i, article in enumerate(news_articles[:5], 1):
                report_lines.append(f"{i}. [{article.get('source', '')}] {article.get('title', '')}")
        else:
            report_lines.append("暂无相关新闻")

        report_lines.append("")

        # 四、综合研判
        report_lines.append("## 四、综合研判")
        report_lines.append("")

        if llm_analysis and llm_analysis.get('analysis'):
            analysis = llm_analysis['analysis']

            report_lines.append(f"- **趋势方向**: {analysis.get('trend', 'N/A')}")
            report_lines.append(f"- **操作建议**: {analysis.get('suggestion', 'N/A')}")

            target_price = analysis.get('target_price', {})
            if target_price:
                short_term = target_price.get('short_term')
                medium_term = target_price.get('medium_term')
                if short_term:
                    report_lines.append(f"- **目标价位**: ${short_term:.2f}（短期）")
                if medium_term:
                    report_lines.append(f"  ${medium_term:.2f}（中期）")

            report_lines.append(f"- **风险等级**: {analysis.get('risk_level', 'N/A')}")
            report_lines.append(f"- **置信度**: {analysis.get('confidence', 'N/A')}")
            report_lines.append("")

            report_lines.append("#### 核心逻辑")
            report_lines.append("")
            report_lines.append(analysis.get('logic', 'N/A'))
            report_lines.append("")

            key_points = analysis.get('key_points', [])
            if key_points:
                report_lines.append("#### 关键要点")
                report_lines.append("")
                for point in key_points:
                    report_lines.append(f"- {point}")
                report_lines.append("")
        else:
            report_lines.append("LLM 分析失败，暂无研判结果")
            report_lines.append("")

        # 免责声明
        report_lines.append("---")
        report_lines.append("")
        report_lines.append("*免责声明: 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。*")
        report_lines.append("")

        return '\n'.join(report_lines)

    def generate_cross_asset_report(self, result: Dict[str, Any]) -> str:
        """生成跨品种联动分析报告（Markdown）

        Args:
            result: CrossAssetAnalyzer.analyze() 的返回值

        Returns:
            Markdown 文本。若无可用数据，返回带说明的占位报告。
        """
        lines: List[str] = []
        lines.append("# 跨品种联动分析")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        symbols = result.get('symbols') or []
        if symbols:
            lines.append(f"**覆盖品种**: {', '.join(symbols)}")
        lines.append("")

        if not result.get('available'):
            lines.append("> 本次运行未获取到足够的跨品种数据，联动分析已跳过。")
            lines.append("")
            return '\n'.join(lines)

        # ---------------- 比价 ----------------
        ratios = result.get('ratios') or []
        if ratios:
            lines.append("## 一、关键比价")
            lines.append("")
            lines.append("| 比价 | 品种对 | 当前值 | 日变动 | 历史分位 | 区间(低~高) | 样本 |")
            lines.append("|---|---|---:|---:|---:|---|---:|")
            for r in ratios:
                pct = r.get('percentile')
                pct_text = f"{pct:.0f}%" if pct == pct else "—"  # NaN != NaN
                lines.append(
                    f"| {r['name']} | {r['pair']} | {r['value']:.2f} | "
                    f"{r['change_percent']:+.2f}% | {pct_text} | "
                    f"{r['window_low']:.2f} ~ {r['window_high']:.2f} | "
                    f"{r['sample_size']} |"
                )
            lines.append("")
            for r in ratios:
                lines.append(f"- **{r['name']}**：{r['note']}")
            lines.append("")

        # ---------------- 相关性 ----------------
        correlations = result.get('correlations') or []
        if correlations:
            window = correlations[0].get('window', 60)
            lines.append(f"## 二、滚动相关性（{window} 日，基于对数收益率）")
            lines.append("")
            lines.append("| 组合 | 当前相关性 | 历史均值 | 偏离(σ) | 先验方向 | 状态 |")
            lines.append("|---|---:|---:|---:|---|---|")
            for c in correlations:
                if c.get('sign_flipped'):
                    status = "⚠ 方向翻转"
                elif c.get('diverged'):
                    status = "⚠ 显著偏离"
                else:
                    status = "正常"
                expected = "负相关" if c['expected'] == 'negative' else "正相关"
                lines.append(
                    f"| {c['pair']} | {c['correlation']:+.3f} | "
                    f"{c['historical_mean']:+.3f} | {c['z_score']:+.2f} | "
                    f"{expected} | {status} |"
                )
            lines.append("")
            lines.append(
                "> 说明：相关性一律基于**对数收益率**计算。直接对价格序列求相关会因"
                "共同趋势产生伪回归，得到虚高的相关系数。"
            )
            lines.append("")

        # ---------------- 提示 ----------------
        alerts = result.get('alerts') or []
        lines.append("## 三、异常提示")
        lines.append("")
        if alerts:
            for a in alerts:
                lines.append(f"- {a}")
        else:
            lines.append("- 本次未发现比价极端值或相关性结构性异常。")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("*免责声明: 本报告仅供参考，不构成投资建议。投资有风险，入市需谨慎。*")
        lines.append("")

        return '\n'.join(lines)

    def save_cross_asset_report(self, content: str) -> str:
        """保存跨品种联动报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = self.output_dir / f"cross_asset_{timestamp}.md"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(filepath)

    def save_report(self, content: str, symbol: str, timeframe: str = "1d") -> str:
        """
        保存报告到文件

        Args:
            content: 报告内容
            symbol: 交易品种代码
            timeframe: 时间周期

        Returns:
            文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"report_{symbol}_{timestamp}.md"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(filepath)

    def generate_json_report(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> str:
        """
        生成 JSON 格式报告

        Args:
            symbol: 交易品种代码
            data: 报告数据字典

        Returns:
            报告内容（JSON 字符串）
        """
        report_data = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'data': data
        }

        return json.dumps(report_data, ensure_ascii=False, indent=2)

    def save_json_report(self, content: str, symbol: str) -> str:
        """
        保存 JSON 报告到文件

        Args:
            content: JSON 报告内容
            symbol: 交易品种代码

        Returns:
            文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"report_{symbol}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return str(filepath)
