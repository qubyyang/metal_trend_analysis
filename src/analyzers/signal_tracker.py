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
    ) -> Dict[str, Any]:
        """回溯评估该品种的历史信号

        Args:
            symbol: 品种代码
            price_df: 日线数据（时间索引，含 close 列）
            direction_field: 评估哪一路信号（technical_direction / llm_direction）

        Returns:
            统计结果字典
        """
        records = [r for r in self.load_all() if r.get("symbol") == symbol]
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

            target_time = entry_time + timedelta(days=record.get("horizon_days", self.horizon_days))

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
                "entry_price": entry_price,
                "exit_price": exit_price,
                "change_pct": round(change_pct, 3),
                "directional_return": round(directional_return, 3),
                "outcome": outcome,
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
            "details": evaluated[-20:],  # 仅保留最近 20 条明细
        }

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
            "",
        ]

        if stats["total_evaluated"] < 30:
            lines.append(
                "> 样本量不足 30 条，统计结果不具备显著性，仅供参考。"
            )
            lines.append("")

        return "\n".join(lines)
