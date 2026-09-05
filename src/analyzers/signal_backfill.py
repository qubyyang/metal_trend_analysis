"""历史信号回填

解决的问题：信号回测需要足够样本才有统计意义（一般 ≥30 条已到期信号），
但靠每日定时任务积累需要数月。本模块用历史 K 线**逐日重放**，
在每个历史交易日重新计算因子评分并生成信号记录，一次拿到数百条样本。

前视偏差的三道防线
------------------

回填最容易犯的错就是让历史信号"看到"了未来数据。这里做了三件事：

1. **截断而非整体计算**。第 i 日的信号只用 ``df.iloc[:i+1]`` 计算，
   引擎拿不到 i 日之后的任何一根 K 线。
2. **指标因果性已验证**。MA / MACD / RSI / 布林带 / ATR 全部基于
   ``rolling`` 与 ``ewm``，二者都是因果算子。实测截断到第 250 行重算，
   与全量计算的第 250 行结果 **逐位相等（diff = 0）**。
   因此本模块只计算一次全量指标再按行切片，是安全的性能优化——
   若未来引入非因果指标（如 ``centered=True`` 的滚动窗口、
   ``zscore`` 全样本标准化），这个前提就会失效，届时必须改回逐日重算。
3. **评估端已有独立防线**。``SignalTracker.evaluate`` 只取
   ``index > entry_time`` 的价格，即使记录有误也不会用到入场当日收盘价。

回填记录带 ``source="backfill"`` 标记，与实盘信号可区分统计——
回填样本没有实盘的执行摩擦（滑点、数据延迟），二者不应混为一谈。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger


class SignalBackfiller:
    """用历史数据重放生成信号记录"""

    def __init__(
        self,
        technical_analyzer,
        tracker,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            technical_analyzer: TechnicalAnalyzer 实例，提供指标与信号引擎
            tracker: SignalTracker 实例，提供存储路径与持有期配置
            config: 回填配置
        """
        self.analyzer = technical_analyzer
        self.tracker = tracker
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        # 前置预热根数：均线/MACD 需要足够历史才稳定，
        # 60 日均线 + MACD 慢线 26 + 信号线 9，取 120 留足余量
        self.warmup = int(self.config.get("warmup_bars", 120))
        # 相邻信号的最小间隔（交易日）。
        #
        # **默认与持有期对齐，而不是逐日采样。** 持有期 5 日却每日采样，
        # 相邻样本的评估窗口重叠 80%，它们不是独立观测。
        # 把 1358 条重叠样本喂给二项检验，会把标准误低估约 sqrt(5) 倍，
        # 于是本不显著的结果看起来 p<0.01——这是回测最常见的自欺方式。
        # 需要更多样本时应拉长历史区间，而不是缩小采样间隔。
        default_step = getattr(tracker, "horizon_days", 5) or 5
        self.step = max(1, int(self.config.get("step_bars", default_step)))

    # ------------------------------------------------------------------
    def backfill(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: str = "1d",
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        """对单个品种回填历史信号

        Args:
            symbol: 品种代码
            df: 原始日线数据（时间索引，含 OHLC）
            timeframe: 时间周期标签
            dry_run: 为 True 时只返回记录、不写入存储

        Returns:
            生成的信号记录列表
        """
        if df is None or df.empty:
            self.logger.warning(f"{symbol} 无历史数据，跳过回填")
            return []

        if len(df) <= self.warmup:
            self.logger.warning(
                f"{symbol} 历史仅 {len(df)} 根，不足预热所需 {self.warmup} 根，跳过"
            )
            return []

        # 指标为因果算子，全量算一次后按行切片即可（见模块文档第 2 点）
        indicators = self.analyzer.calculate_all_indicators(df)
        engine = self.analyzer.signal_engine

        existing = self._existing_keys(symbol)
        records: List[Dict[str, Any]] = []
        skipped = 0

        for i in range(self.warmup, len(indicators), self.step):
            window = indicators.iloc[: i + 1]
            bar_time = window.index[-1]

            key = (symbol, pd.Timestamp(bar_time).strftime("%Y-%m-%d"))
            if key in existing:
                skipped += 1
                continue

            result = engine.evaluate(window)
            if not result.get("available"):
                continue

            entry_price = float(window["close"].iloc[-1])
            if entry_price <= 0:
                continue

            direction = result.get("direction", "neutral")
            record = {
                "signal_id": f"{symbol}_bf_{pd.Timestamp(bar_time).strftime('%Y%m%d')}",
                "symbol": symbol,
                "timeframe": timeframe,
                # 用 K 线时间而非当前时间，评估时才能正确匹配未来价格
                "created_at": pd.Timestamp(bar_time).isoformat(),
                "entry_price": entry_price,
                "technical_direction": self._coarse(direction),
                "signal_score": result.get("score"),
                "signal_direction": direction,
                "signal_confidence": result.get("confidence"),
                "llm_direction": None,
                "macd_signal": None,
                "rsi": self._safe_float(window.get("RSI", pd.Series()).iloc[-1]
                                        if "RSI" in window.columns else None),
                "rsi_signal": None,
                "ma_alignment": None,
                "horizon_days": self.tracker.horizon_days,
                "evaluated": False,
                # 回填样本无执行摩擦，统计时应与实盘信号区分
                "source": "backfill",
            }
            records.append(record)

        if skipped:
            self.logger.info(f"{symbol} 跳过 {skipped} 条已存在的同日信号")

        if records and not dry_run:
            self._append_all(records)

        self.logger.info(
            f"{symbol} 回填 {len(records)} 条信号"
            f"（{records[0]['created_at'][:10]} ~ {records[-1]['created_at'][:10]}）"
            if records else f"{symbol} 未生成新信号"
        )
        return records

    # ------------------------------------------------------------------
    @staticmethod
    def _coarse(direction: str) -> str:
        """strong_bullish / bullish -> bullish，供旧的 technical_direction 字段消费"""
        if direction.endswith("bullish"):
            return "bullish"
        if direction.endswith("bearish"):
            return "bearish"
        return "neutral"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if pd.notna(value) else None

    def _existing_keys(self, symbol: str) -> set:
        """已有记录的 (品种, 日期) 集合，用于幂等——重复回填不产生重复样本"""
        keys = set()
        for record in self.tracker.load_all():
            if record.get("symbol") != symbol:
                continue
            created = str(record.get("created_at", ""))[:10]
            if created:
                keys.add((symbol, created))
        return keys

    def _append_all(self, records: List[Dict[str, Any]]) -> None:
        path = Path(self.tracker.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
