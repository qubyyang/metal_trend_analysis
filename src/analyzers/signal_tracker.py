"""
信号追踪与回测模块

解决的问题：系统每天输出趋势研判，但从未验证过这些判断是否准确。
本模块持久化每次信号，在持有期结束后用实际价格回溯校验，
输出胜率、盈亏比、期望收益等统计，用于判断策略是否具备真实 alpha。

设计原则：
- 信号一经记录不可篡改，评估结果单独写入，保证可审计
- 仅使用信号发出「之后」的价格进行评估，杜绝前视偏差
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

# 方向映射：把各处的中英文表述统一为 bullish / bearish / neutral
DIRECTION_ALIASES = {
    "bullish": "bullish", "看涨": "bullish", "多头": "bullish", "buy": "bullish",
    "bearish": "bearish", "看跌": "bearish", "空头": "bearish", "sell": "bearish",
    "neutral": "neutral", "中性": "neutral", "震荡": "neutral", "hold": "neutral",
}


def normalize_direction(value: Any) -> str:
    """把任意趋势表述归一化为 bullish / bearish / neutral"""
    if not value:
        return "neutral"

    text = str(value).strip().lower()
    if text in DIRECTION_ALIASES:
        return DIRECTION_ALIASES[text]

    for alias, canonical in DIRECTION_ALIASES.items():
        if alias in text:
            return canonical

    return "neutral"


class SignalTracker:
    """信号记录与回测评估器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        self.store_path = Path(self.config.get("signal_store", "data/signals/signals.jsonl"))
        # 持有期（自然日）：信号发出后多久评估
        self.horizon_days = int(self.config.get("horizon_days", 5))
        # 判定为有效方向变动的最小幅度，过滤噪声
        self.threshold_pct = float(self.config.get("threshold_pct", 0.5))

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------
    def record(
        self,
        symbol: str,
        quote_data: Dict[str, Any],
        technical_data: Dict[str, Any],
        llm_analysis: Optional[Dict[str, Any]] = None,
        timeframe: str = "1d",
    ) -> Optional[Dict[str, Any]]:
        """记录一次趋势研判信号

        Returns:
            写入的信号记录；数据不足时返回 None
        """
        price = quote_data.get("price") if quote_data else None
        if not price:
            self.logger.warning(f"{symbol} 缺少价格，跳过信号记录")
            return None

        llm_direction = None
        if llm_analysis:
            analysis = llm_analysis.get("analysis") or {}
            if isinstance(analysis, dict):
                llm_direction = analysis.get("trend")

        record = {
            "signal_id": f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "symbol": symbol,
            "timeframe": timeframe,
            "created_at": datetime.now().isoformat(),
            "entry_price": float(price),
            "technical_direction": normalize_direction(technical_data.get("trend")),
            # 因子化引擎的连续评分与置信度。留存原始值是为了后续能按
            # 「强信号 vs 弱信号」分层统计胜率，验证评分是否真的有区分度。
            "signal_score": technical_data.get("signal_score"),
            "signal_direction": technical_data.get("signal_direction"),
            "signal_confidence": technical_data.get("signal_confidence"),
            "llm_direction": normalize_direction(llm_direction) if llm_direction else None,
            "macd_signal": technical_data.get("macd_signal"),
            "rsi": technical_data.get("rsi"),
            "rsi_signal": technical_data.get("rsi_signal"),
            "ma_alignment": technical_data.get("ma_alignment"),
            "horizon_days": self.horizon_days,
            "evaluated": False,
        }

        self._append(record)
        self.logger.info(
            f"{symbol} 信号已记录: {record['technical_direction']} @ ${price:.2f}"
        )
        return record

    def _append(self, record: Dict[str, Any]) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def load_all(self) -> List[Dict[str, Any]]:
        """读取全部信号记录"""
        if not self.store_path.exists():
            return []

        records = []
        with open(self.store_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    self.logger.warning(f"信号文件第 {line_no} 行解析失败，已跳过")
        return records

    # ------------------------------------------------------------------
    # 评估
    # ------------------------------------------------------------------
    def evaluate(
        self,
        symbol: str,
        price_df: pd.DataFrame,
        direction_field: str = "technical_direction",
        horizon_days: Optional[int] = None,
        source: Optional[str] = None,
    ) -> Dict[str, Any]:
        """回溯评估该品种的历史信号

        Args:
            symbol: 品种代码
            price_df: 日线数据（时间索引，含 close 列）
            direction_field: 评估哪一路信号（technical_direction / llm_direction）
            horizon_days: 覆盖记录自带的持有期，用于绘制衰减曲线
            source: 只评估指定来源的信号（live / backfill），None 表示全部

        Returns:
            统计结果字典
        """
        records = [r for r in self.load_all() if r.get("symbol") == symbol]
        if source is not None:
            records = [
                r for r in records if (r.get("source") or "live") == source
            ]
        if not records or price_df is None or price_df.empty:
            return self._empty_stats(symbol, direction_field)

        closes = price_df["close"].sort_index()
        evaluated: List[Dict[str, Any]] = []

        for record in records:
            direction = record.get(direction_field)
            if not direction or direction == "neutral":
                continue

            try:
                entry_time = pd.Timestamp(record["created_at"]).tz_localize(None)
            except Exception:
                continue

            span = horizon_days if horizon_days is not None else record.get(
                "horizon_days", self.horizon_days
            )
            target_time = entry_time + timedelta(days=span)

            # 严格使用信号之后的价格，避免前视偏差
            future = closes[closes.index > entry_time]
            if future.empty:
                continue

            settled = future[future.index >= target_time]
            if settled.empty:
                # 持有期尚未结束
                continue

            exit_price = float(settled.iloc[0])
            entry_price = float(record["entry_price"])
            if not entry_price:
                continue

            change_pct = (exit_price - entry_price) / entry_price * 100

            if abs(change_pct) < self.threshold_pct:
                outcome = "flat"
            elif (direction == "bullish" and change_pct > 0) or \
                 (direction == "bearish" and change_pct < 0):
                outcome = "win"
            else:
                outcome = "loss"

            # 方向收益：看跌信号下跌同样算正收益
            directional_return = change_pct if direction == "bullish" else -change_pct

            evaluated.append({
                "signal_id": record["signal_id"],
                "direction": direction,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "change_pct": round(change_pct, 3),
                "directional_return": round(directional_return, 3),
                "outcome": outcome,
                "signal_score": record.get("signal_score"),
                "source": record.get("source") or "live",
            })

        return self._summarize(symbol, direction_field, evaluated)

    def _summarize(
        self, symbol: str, direction_field: str, evaluated: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """汇总统计指标"""
        if not evaluated:
            return self._empty_stats(symbol, direction_field)

        wins = [e for e in evaluated if e["outcome"] == "win"]
        losses = [e for e in evaluated if e["outcome"] == "loss"]
        flats = [e for e in evaluated if e["outcome"] == "flat"]

        decisive = len(wins) + len(losses)
        win_rate = (len(wins) / decisive * 100) if decisive else 0.0

        avg_win = sum(e["directional_return"] for e in wins) / len(wins) if wins else 0.0
        avg_loss = sum(e["directional_return"] for e in losses) / len(losses) if losses else 0.0
        profit_factor = abs(avg_win / avg_loss) if avg_loss else None

        returns = [e["directional_return"] for e in evaluated]
        avg_return = sum(returns) / len(returns)

        return {
            "symbol": symbol,
            "direction_field": direction_field,
            "total_evaluated": len(evaluated),
            "wins": len(wins),
            "losses": len(losses),
            "flats": len(flats),
            "win_rate": round(win_rate, 2),
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "profit_factor": round(profit_factor, 2) if profit_factor else None,
            "avg_return_pct": round(avg_return, 3),
            "cumulative_return_pct": round(sum(returns), 3),
            "max_drawdown_pct": self._max_drawdown(evaluated),
            "significance": self._significance(len(wins), decisive),
            "score_buckets": self._score_buckets(evaluated),
            # details 供报告/序列化消费，Timestamp 转字符串避免 JSON 序列化失败
            "details": [
                {**e, "entry_time": str(e.get("entry_time", ""))}
                for e in evaluated[-20:]
            ],
        }

    # ------------------------------------------------------------------
    # 扩展统计
    # ------------------------------------------------------------------
    @staticmethod
    def _max_drawdown(evaluated: List[Dict[str, Any]]) -> float:
        """按信号时间顺序累计方向收益，取最大回撤

        注意这是**信号序列的回撤**，不是真实账户回撤——
        它假设每次信号等权、独立建仓，忽略了持有期重叠与仓位管理。
        用途是衡量策略连续失误的深度，而非预测实际资金曲线。
        """
        if not evaluated:
            return 0.0

        ordered = sorted(
            evaluated,
            key=lambda e: e.get("entry_time") or pd.Timestamp.min,
        )

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for item in ordered:
            cumulative += item["directional_return"]
            peak = max(peak, cumulative)
            max_dd = min(max_dd, cumulative - peak)

        return round(max_dd, 3)

    @staticmethod
    def _significance(wins: int, decisive: int) -> Dict[str, Any]:
        """检验胜率是否显著优于抛硬币

        用二项检验的正态近似：H0 为 p=0.5，统计量
        ``z = (k - n/2) / sqrt(n/4)``。样本 < 30 时正态近似不可靠，
        直接标记为样本不足而非给出误导性的 p 值。

        这一步是必要的：50 条信号里 28 胜 22 负看着像有 alpha，
        实际 z≈0.85、p≈0.40，与随机无异。
        """
        if decisive < 30:
            return {
                "sufficient_sample": False,
                "z_score": None,
                "p_value": None,
                "verdict": f"样本 {decisive} 条不足 30，无法判定显著性",
            }

        expected = decisive / 2.0
        std = (decisive / 4.0) ** 0.5
        z = (wins - expected) / std if std else 0.0

        # 双尾 p 值：用误差函数计算标准正态尾部概率
        p = math.erfc(abs(z) / math.sqrt(2))

        if p < 0.05:
            verdict = (
                f"胜率显著{'优于' if z > 0 else '劣于'}随机"
                f"（z={z:+.2f}, p={p:.4f}）"
            )
        else:
            verdict = f"与随机无显著差异（z={z:+.2f}, p={p:.4f}），暂不能认定存在 alpha"

        return {
            "sufficient_sample": True,
            "z_score": round(z, 3),
            "p_value": round(p, 4),
            "verdict": verdict,
        }

    @staticmethod
    def _score_buckets(evaluated: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按信号评分强度分层统计胜率

        这是验证因子化评分是否真有区分度的核心检验：
        若强信号的胜率并不高于弱信号，说明评分只是噪声的重新包装，
        分层展示比一个笼统的总胜率更能暴露问题。
        """
        scored = [
            e for e in evaluated
            if e.get("signal_score") is not None and e["outcome"] in ("win", "loss")
        ]
        if not scored:
            return []

        bands = [
            ("强信号 |score|>=40", lambda s: abs(s) >= 40),
            ("中等 15<=|score|<40", lambda s: 15 <= abs(s) < 40),
            ("弱信号 |score|<15", lambda s: abs(s) < 15),
        ]

        buckets = []
        for label, predicate in bands:
            items = [e for e in scored if predicate(float(e["signal_score"]))]
            if not items:
                continue
            wins = sum(1 for e in items if e["outcome"] == "win")
            returns = [e["directional_return"] for e in items]
            buckets.append({
                "band": label,
                "count": len(items),
                "win_rate": round(wins / len(items) * 100, 2),
                "avg_return_pct": round(sum(returns) / len(returns), 3),
            })
        return buckets

    def benchmark(
        self,
        price_df: pd.DataFrame,
        horizon_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """买入持有基准：同期任意日做多、持有相同天数的表现

        **没有这个基准，胜率数字毫无意义。** 一个在牛市里只会喊多的策略
        很容易做到 55% 胜率，但那是 beta 不是 alpha。只有当策略的
        期望收益显著高于「随便哪天买入并持有同样久」时，
        择时才创造了价值。

        本项目的实测结果就是反例：黄金策略期望 +0.11%/5 日，
        而买入持有基准是 +0.32%——择时反而毁灭了价值。
        """
        if price_df is None or price_df.empty or "close" not in price_df.columns:
            return {"available": False}

        days = horizon_days or self.horizon_days
        closes = pd.to_numeric(price_df["close"], errors="coerce").dropna()
        if len(closes) <= days:
            return {"available": False}

        # 用交易日位移近似自然日持有期。二者在日线上基本等价，
        # 且避免了节假日导致的样本缺失。
        forward = (closes.shift(-days) / closes - 1.0) * 100
        forward = forward.dropna()
        if forward.empty:
            return {"available": False}

        up_rate = float((forward > self.threshold_pct).mean() * 100)
        return {
            "available": True,
            "horizon_days": days,
            "samples": len(forward),
            "up_rate": round(up_rate, 2),
            "avg_return_pct": round(float(forward.mean()), 3),
            "median_return_pct": round(float(forward.median()), 3),
        }

    @staticmethod
    def format_benchmark(
        symbol: str, stats: Dict[str, Any], benchmark: Dict[str, Any]
    ) -> str:
        """把策略与买入持有基准并列展示"""
        if not benchmark.get("available") or stats.get("total_evaluated", 0) == 0:
            return ""

        edge = stats["avg_return_pct"] - benchmark["avg_return_pct"]
        if edge > 0.05:
            verdict = f"择时创造了 {edge:+.3f}% 的超额，方向正确但幅度有限"
        elif edge < -0.05:
            verdict = (
                f"择时**跑输**买入持有 {abs(edge):.3f}%，"
                "当前信号未能创造价值，不应据此实盘"
            )
        else:
            verdict = "与买入持有基本持平，择时未产生可辨识的贡献"

        return "\n".join([
            f"### 策略 vs 买入持有 · {symbol}",
            "",
            f"| 口径 | 样本 | 胜率/上涨率 | 期望收益（{benchmark['horizon_days']} 日） |",
            "|------|------|------------|--------------|",
            f"| 策略择时 | {stats['total_evaluated']} | {stats['win_rate']:.1f}% | "
            f"{stats['avg_return_pct']:+.3f}% |",
            f"| 买入持有 | {benchmark['samples']} | {benchmark['up_rate']:.1f}% | "
            f"{benchmark['avg_return_pct']:+.3f}% |",
            "",
            f"**结论**: {verdict}",
            "",
            "> 胜率脱离基准无意义：牛市里只喊多也能有 55% 胜率，那是 beta 不是 alpha。",
            "",
        ])

    def decay_curve(
        self,
        symbol: str,
        price_df: pd.DataFrame,
        horizons: Optional[List[int]] = None,
        direction_field: str = "technical_direction",
    ) -> List[Dict[str, Any]]:
        """不同持有期下的胜率与收益，用于观察信号衰减

        信号的预测力通常随时间衰减。若 1 日胜率 60%、20 日回落到 50%，
        说明信号捕捉的是短期动量而非趋势；反之若长周期才显现优势，
        则当前 5 日的持有期设置偏短。
        """
        horizons = horizons or [1, 3, 5, 10, 20]
        curve = []
        for days in horizons:
            stats = self.evaluate(
                symbol, price_df, direction_field=direction_field, horizon_days=days
            )
            curve.append({
                "horizon_days": days,
                "evaluated": stats["total_evaluated"],
                "win_rate": stats["win_rate"],
                "avg_return_pct": stats["avg_return_pct"],
                "profit_factor": stats["profit_factor"],
            })
        return curve

    @staticmethod
    def _empty_stats(symbol: str, direction_field: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "direction_field": direction_field,
            "total_evaluated": 0,
            "wins": 0,
            "losses": 0,
            "flats": 0,
            "win_rate": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "profit_factor": None,
            "avg_return_pct": 0.0,
            "cumulative_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "significance": {
                "sufficient_sample": False,
                "z_score": None,
                "p_value": None,
                "verdict": "无已评估样本",
            },
            "score_buckets": [],
            "details": [],
        }

    # ------------------------------------------------------------------
    def format_report(self, stats: Dict[str, Any]) -> str:
        """把统计结果格式化为 Markdown 片段"""
        if stats["total_evaluated"] == 0:
            return (
                f"### 信号准确率 · {stats['symbol']}\n\n"
                "暂无已到期的信号可供评估。\n"
            )

        pf = stats["profit_factor"]
        pf_text = f"{pf:.2f}" if pf is not None else "N/A"

        lines = [
            f"### 信号准确率 · {stats['symbol']}",
            "",
            f"- 已评估信号: {stats['total_evaluated']} 条"
            f"（胜 {stats['wins']} / 负 {stats['losses']} / 平 {stats['flats']}）",
            f"- 胜率: **{stats['win_rate']:.2f}%**",
            f"- 平均盈利: {stats['avg_win_pct']:+.2f}% ｜ 平均亏损: {stats['avg_loss_pct']:+.2f}%",
            f"- 盈亏比: {pf_text}",
            f"- 单次期望收益: {stats['avg_return_pct']:+.2f}%",
            f"- 累计方向收益: {stats['cumulative_return_pct']:+.2f}%",
            f"- 最大回撤: {stats.get('max_drawdown_pct', 0.0):.2f}%"
            "（信号序列等权累计，非真实账户回撤）",
            "",
        ]

        significance = stats.get("significance") or {}
        if significance.get("verdict"):
            lines.append(f"**显著性检验**: {significance['verdict']}")
            lines.append("")

        buckets = stats.get("score_buckets") or []
        if buckets:
            lines.extend([
                "**按信号强度分层**",
                "",
                "| 强度区间 | 样本 | 胜率 | 平均收益 |",
                "|---------|------|------|---------|",
            ])
            for bucket in buckets:
                lines.append(
                    f"| {bucket['band']} | {bucket['count']} | "
                    f"{bucket['win_rate']:.1f}% | {bucket['avg_return_pct']:+.2f}% |"
                )
            lines.append("")
            lines.append(
                "> 若强信号胜率未高于弱信号，说明评分缺乏区分度，"
                "需回头检查因子权重设置。"
            )
            lines.append("")

        if stats["total_evaluated"] < 30:
            lines.append(
                "> 样本量不足 30 条，统计结果不具备显著性，仅供参考。"
            )
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def format_decay_curve(symbol: str, curve: List[Dict[str, Any]]) -> str:
        """把衰减曲线渲染为 Markdown 表格"""
        if not curve or all(c["evaluated"] == 0 for c in curve):
            return ""

        lines = [
            f"### 信号衰减曲线 · {symbol}",
            "",
            "| 持有期 | 样本 | 胜率 | 平均收益 | 盈亏比 |",
            "|-------|------|------|---------|--------|",
        ]
        for point in curve:
            pf = point["profit_factor"]
            pf_text = f"{pf:.2f}" if pf is not None else "N/A"
            lines.append(
                f"| {point['horizon_days']} 日 | {point['evaluated']} | "
                f"{point['win_rate']:.1f}% | {point['avg_return_pct']:+.2f}% | {pf_text} |"
            )
        lines.extend([
            "",
            "> 胜率随持有期快速回落说明信号捕捉的是短期动量；"
            "若长周期才显现优势，则当前持有期设置偏短。",
            "",
        ])
        return "\n".join(lines)
