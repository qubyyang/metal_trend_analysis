"""
行情数据源抽象基类

所有数据源（Stooq、Yahoo Finance 等）实现统一接口，
由 MarketDataClient 负责主源/备源的降级调度。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from ..utils.exceptions import DataFetchError, ValidationError

# 统一的 K 线列定义
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class BaseDataProvider(ABC):
    """行情数据源基类

    子类必须实现 ``name``、``supports`` 与 ``fetch_daily``。
    报价与重采样逻辑由基类统一实现，避免各数据源重复。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.timeout = self.config.get("timeout", 20)
        self.default_kline_count = self.config.get("default_kline_count", 200)
        self.logger = logger.bind(name=self.__class__.__name__)

    # ------------------------------------------------------------------
    # 子类需实现的接口
    # ------------------------------------------------------------------
    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称，用于日志与降级追踪"""

    @abstractmethod
    def fetch_daily(self, symbol: str) -> pd.DataFrame:
        """获取日线数据

        Args:
            symbol: 通用品种代码，如 ``XAUUSD``

        Returns:
            以时间为索引、包含 OHLCV_COLUMNS 的 DataFrame（升序）

        Raises:
            DataFetchError: 数据获取或解析失败
        """

    def supports(self, symbol: str) -> bool:
        """该数据源是否支持指定品种，默认全部支持"""
        return bool(symbol)

    # ------------------------------------------------------------------
    # 通用能力
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        """规范化周期字符串，未知值回退为日线"""
        if not timeframe or not isinstance(timeframe, str):
            return "1d"

        normalized = timeframe.lower().strip()
        if normalized in {"1d", "d", "day", "daily"}:
            return "1d"
        if normalized in {"1w", "1wk", "w", "week", "weekly"}:
            return "1w"
        if normalized in {"1m", "1mo", "mo", "month", "monthly"}:
            return "1m"
        return "1d"

    def _standardize(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """校验并标准化 DataFrame 结构"""
        if df is None or df.empty:
            raise DataFetchError(f"[{self.name}] 未获取到 {symbol} 的数据")

        missing = [c for c in ("open", "high", "low", "close") if c not in df.columns]
        if missing:
            raise DataFetchError(f"[{self.name}] {symbol} 数据缺少列: {missing}")

        result = df.copy()
        if "volume" not in result.columns:
            result["volume"] = 0

        result = result[OHLCV_COLUMNS]
        result = result.apply(pd.to_numeric, errors="coerce")
        result = result.dropna(subset=["open", "high", "low", "close"])

        if result.empty:
            raise DataFetchError(f"[{self.name}] {symbol} 数据清洗后为空")

        result = result[~result.index.duplicated(keep="last")].sort_index()
        return result

    def resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """将日线重采样为周线或月线"""
        normalized = self._normalize_timeframe(timeframe)
        if normalized == "1d" or df.empty:
            return df

        rule = "W-FRI" if normalized == "1w" else "ME"

        try:
            resampled = df.resample(rule).agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            })
            return resampled.dropna(subset=["open", "high", "low", "close"])
        except Exception as e:  # pragma: no cover - 理论上不应触发
            self.logger.error(f"重采样到 {normalized} 失败: {e}")
            return df

    def get_kline(
        self,
        symbol: str,
        timeframe: str = "1d",
        count: Optional[int] = None,
    ) -> pd.DataFrame:
        """获取指定周期的 K 线数据"""
        if not symbol:
            raise ValidationError("symbol 不能为空")

        if count is None:
            count = self.default_kline_count
        elif count <= 0:
            raise ValidationError(f"count 必须为正数，当前值: {count}")

        df = self._standardize(self.fetch_daily(symbol), symbol)
        df = self.resample(df, timeframe)

        if len(df) > count:
            df = df.tail(count)

        return df

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """基于最新日线收盘价构造报价"""
        df = self._standardize(self.fetch_daily(symbol), symbol)

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        prev_close = float(prev["close"])
        change = float(latest["close"]) - prev_close
        change_percent = (change / prev_close * 100) if prev_close else 0.0

        return {
            "symbol": symbol,
            "price": float(latest["close"]),
            "change": change,
            "change_percent": change_percent,
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "volume": float(latest["volume"]),
            "source": self.name,
            "bar_time": df.index[-1].isoformat(),
            "timestamp": datetime.now().isoformat(),
        }
