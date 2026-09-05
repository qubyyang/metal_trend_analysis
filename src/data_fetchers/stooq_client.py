"""
Stooq data client (free, daily data)

.. deprecated::
    本模块已由 ``StooqProvider`` + ``MarketDataClient`` 取代，后者支持
    多数据源自动降级与缓存兜底。保留一个版本周期以兼容外部引用，
    新代码请使用 ``src.data_fetchers.market_data.MarketDataClient``。
"""
from __future__ import annotations

import warnings
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import requests
from loguru import logger

from ..utils.exceptions import DataFetchError, NetworkError, ValidationError
from ..utils.common import with_retry, validate_config


class StooqClient:
    """Stooq 数据客户端（免费、无需 API Key）"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Stooq 客户端

        Args:
            config: Stooq 配置字典

        Raises:
            ValidationError: 配置无效时抛出
        """
        self.logger = logger.bind(name=self.__class__.__name__)

        # Validate configuration
        validate_config(config, [], "StooqClient config")

        self.base_url = config.get("base_url", "https://stooq.com/q/d/l/")
        self.timeout = config.get("timeout", 20)
        self.retry = config.get("retry", 3)
        self.retry_delay = config.get("retry_delay", 2)
        self.default_kline_count = config.get("default_kline_count", 200)

        self.logger.info(f"Stooq client initialized with base_url: {self.base_url}")

    @with_retry(max_attempts=3, exceptions=(NetworkError, requests.RequestException))
    def _request_csv(self, symbol: str) -> pd.DataFrame:
        """
        获取 Stooq CSV 数据（默认日线）

        Args:
            symbol: Stooq 品种代码 (如 xauusd, xagusd)

        Returns:
            日线数据 DataFrame

        Raises:
            NetworkError: 网络请求失败
            DataFetchError: 数据获取失败
        """
        if not symbol or not isinstance(symbol, str):
            raise ValidationError(f"Invalid symbol: {symbol}")

        params = {
            "s": symbol.lower(),
            "i": "d",
        }

        try:
            self.logger.debug(f"Requesting data for symbol: {symbol}")
            response = requests.get(self.base_url, params=params, timeout=self.timeout)
            response.raise_for_status()

            if "No data" in response.text or not response.text.strip():
                raise DataFetchError(f"Stooq returned no data for symbol: {symbol}")

            df = pd.read_csv(StringIO(response.text))
            if df.empty:
                raise DataFetchError(f"Empty DataFrame for symbol: {symbol}")

            # Validate required columns
            required_columns = ['Date', 'Open', 'High', 'Low', 'Close']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise DataFetchError(f"Missing columns in data: {missing_columns}")

            # Process data
            df["Date"] = pd.to_datetime(df["Date"])
            df.rename(
                columns={
                    "Date": "timestamp",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                },
                inplace=True,
            )

            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            df["volume"] = 0

            self.logger.debug(f"Successfully fetched {len(df)} records for {symbol}")
            return df

        except requests.RequestException as e:
            raise NetworkError(f"Network error fetching data for {symbol}: {e}")
        except pd.errors.EmptyDataError as e:
            raise DataFetchError(f"Invalid CSV data for {symbol}: {e}")
        except Exception as e:
            raise DataFetchError(f"Unexpected error fetching data for {symbol}: {e}")

    def _normalize_timeframe(self, timeframe: str) -> str:
        """
        规范化时间周期

        Args:
            timeframe: 原始时间周期字符串

        Returns:
            规范化的时间周期
        """
        if not timeframe or not isinstance(timeframe, str):
            self.logger.warning(f"Invalid timeframe: {timeframe}, defaulting to '1d'")
            return "1d"

        normalized = timeframe.lower().strip()
        if normalized in {"1d", "d", "day"}:
            return "1d"
        if normalized in {"1w", "1wk", "week"}:
            return "1w"
        if normalized in {"1m", "1mo", "month"}:
            return "1m"

        self.logger.warning(f"Unknown timeframe: {timeframe}, defaulting to '1d'")
        return "1d"

    def _resample(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        将日线数据重采样为周线/月线

        Args:
            df: 日线数据
            timeframe: 目标时间周期

        Returns:
            重采样后的数据
        """
        if timeframe == "1w":
            rule = "W-FRI"
        elif timeframe == "1m":
            rule = "M"
        else:
            return df

        try:
            resampled = pd.DataFrame()
            resampled["open"] = df["open"].resample(rule).first()
            resampled["high"] = df["high"].resample(rule).max()
            resampled["low"] = df["low"].resample(rule).min()
            resampled["close"] = df["close"].resample(rule).last()
            resampled["volume"] = 0
            resampled.dropna(inplace=True)

            self.logger.debug(f"Resampled data to {timeframe}: {len(resampled)} records")
            return resampled

        except Exception as e:
            self.logger.error(f"Error resampling data to {timeframe}: {e}")
            return df

    def get_quote(self, symbol: str, region: str | None = None) -> Dict[str, Any]:
        """
        获取最新报价（基于 Stooq 日线收盘）

        Args:
            symbol: 交易品种代码
            region: 未使用（保持接口兼容）

        Returns:
            报价数据字典，如果失败返回空字典

        Raises:
            ValidationError: 参数无效
            DataFetchError: 数据获取失败
        """
        if not symbol:
            raise ValidationError("Symbol cannot be empty")

        try:
            stooq_symbol = symbol.lower()
            df = self._request_csv(stooq_symbol)

            if df.empty:
                raise DataFetchError(f"No data available for symbol: {symbol}")

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest

            change = latest["close"] - prev["close"]
            change_percent = (change / prev["close"] * 100) if prev["close"] else 0

            quote_data = {
                "symbol": symbol,
                "price": float(latest["close"]),
                "change": float(change),
                "change_percent": float(change_percent),
                "high": float(latest["high"]),
                "low": float(latest["low"]),
                "open": float(latest["open"]),
                "volume": 0,
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info(f"Quote data retrieved for {symbol}: ${quote_data['price']}")
            return quote_data

        except (DataFetchError, ValidationError):
            raise
        except Exception as e:
            raise DataFetchError(f"Unexpected error getting quote for {symbol}: {e}")

    def get_kline(
        self,
        symbol: str,
        timeframe: str = "1d",
        count: Optional[int] = None,
        region: str | None = None,
    ) -> pd.DataFrame:
        """
        获取 K 线数据（Stooq 仅提供日线，支持周/月线重采样）

        Args:
            symbol: 交易品种代码
            timeframe: 时间周期 (1d/1w/1m)
            count: 返回条数
            region: 未使用（保持接口兼容）

        Returns:
            K 线数据 DataFrame

        Raises:
            ValidationError: 参数无效
            DataFetchError: 数据获取失败
        """
        if not symbol:
            raise ValidationError("Symbol cannot be empty")

        if count is None:
            count = self.default_kline_count
        elif count <= 0:
            raise ValidationError(f"Count must be positive, got: {count}")

        try:
            stooq_symbol = symbol.lower()
            df = self._request_csv(stooq_symbol)
            normalized = self._normalize_timeframe(timeframe)

            df = self._resample(df, normalized)

            if len(df) > count:
                df = df.tail(count)

            self.logger.info(f"K-line data retrieved for {symbol}: {len(df)} records ({normalized})")
            return df

        except (DataFetchError, ValidationError):
            raise
        except Exception as e:
            raise DataFetchError(f"Unexpected error getting K-line data for {symbol}: {e}")

    def save_raw_data(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Path]:
        """
        保存原始数据到文件

        Args:
            df: 要保存的数据
            symbol: 交易品种代码
            timeframe: 时间周期

        Returns:
            保存的文件路径，失败时返回 None
        """
        try:
            if df.empty:
                self.logger.warning(f"No data to save for {symbol}")
                return None

            output_dir = Path("data/raw")
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{symbol}_{timeframe}_{timestamp}.csv"
            filepath = output_dir / filename

            df.to_csv(filepath)
            self.logger.info(f"Raw data saved: {filepath}")
            return filepath

        except Exception as e:
            self.logger.error(f"Error saving raw data for {symbol}: {e}")
            return None
