"""
Yahoo Finance 数据源提供器（备用源）

使用公开的 chart JSON 接口，无需 API Key。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError, NetworkError
from .base_provider import BaseDataProvider

# 通用代码 -> Yahoo Finance 代码
SYMBOL_MAP = {
    "XAUUSD": "GC=F",   # COMEX 黄金期货
    "XAGUSD": "SI=F",   # COMEX 白银期货
}


class YahooProvider(BaseDataProvider):
    """Yahoo Finance 日线数据源"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get(
            "base_url", "https://query1.finance.yahoo.com/v8/finance/chart/"
        )
        self.range = self.config.get("range", "2y")

    @property
    def name(self) -> str:
        return "yahoo"

    def _resolve_symbol(self, symbol: str) -> str:
        return SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    def fetch_daily(self, symbol: str) -> pd.DataFrame:
        yahoo_symbol = self._resolve_symbol(symbol)
        url = f"{self.base_url}{yahoo_symbol}"

        try:
            response = requests.get(
                url,
                params={"range": self.range, "interval": "1d"},
                timeout=self.timeout,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MetalTrendAI/1.0)"},
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as e:
            raise NetworkError(f"[yahoo] 请求 {symbol} 失败: {e}")
        except ValueError as e:
            raise DataFetchError(f"[yahoo] {symbol} 响应非合法 JSON: {e}")

        chart = (payload or {}).get("chart") or {}
        if chart.get("error"):
            raise DataFetchError(f"[yahoo] {symbol} 接口返回错误: {chart['error']}")

        results = chart.get("result") or []
        if not results:
            raise DataFetchError(f"[yahoo] {symbol} 无数据返回")

        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]

        if not timestamps or not quotes:
            raise DataFetchError(f"[yahoo] {symbol} 数据字段缺失")

        df = pd.DataFrame({
            "open": quotes.get("open"),
            "high": quotes.get("high"),
            "low": quotes.get("low"),
            "close": quotes.get("close"),
            "volume": quotes.get("volume"),
        }, index=pd.to_datetime(timestamps, unit="s"))
        df.index.name = "timestamp"

        return df
