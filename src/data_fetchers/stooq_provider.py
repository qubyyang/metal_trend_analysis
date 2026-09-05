"""
Stooq 数据源提供器（主源，免费、无需 API Key）
"""
from __future__ import annotations

from io import StringIO
from typing import Any, Dict, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError, NetworkError
from .base_provider import BaseDataProvider

# 通用代码 -> Stooq 代码
SYMBOL_MAP = {
    "XAUUSD": "xauusd",
    "XAGUSD": "xagusd",
}


class StooqProvider(BaseDataProvider):
    """Stooq 日线数据源"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get("base_url", "https://stooq.com/q/d/l/")

    @property
    def name(self) -> str:
        return "stooq"

    def _resolve_symbol(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol.upper(), symbol.lower())

    def fetch_daily(self, symbol: str) -> pd.DataFrame:
        stooq_symbol = self._resolve_symbol(symbol)

        try:
            response = requests.get(
                self.base_url,
                params={"s": stooq_symbol, "i": "d"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise NetworkError(f"[stooq] 请求 {symbol} 失败: {e}")

        text = response.text
        if not text.strip() or "No data" in text:
            raise DataFetchError(f"[stooq] {symbol} 无数据返回")

        try:
            df = pd.read_csv(StringIO(text))
        except Exception as e:
            raise DataFetchError(f"[stooq] {symbol} CSV 解析失败: {e}")

        if df.empty or "Date" not in df.columns:
            raise DataFetchError(f"[stooq] {symbol} 返回数据格式异常")

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.rename(columns={
            "Date": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }).set_index("timestamp")

        return df
