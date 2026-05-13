"""
Stooq data client (free, daily data) with yfinance fallback
"""
from __future__ import annotations

from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import requests
import yfinance as yf
from loguru import logger

from ..utils.exceptions import DataFetchError, NetworkError, ValidationError
from ..utils.common import with_retry, validate_config


class StooqClient:
    """Stooq 数据客户端（免费、无需 API Key），失败时回退 yfinance"""

    def __init__(self, config: Dict[str, Any]):
        self.logger = logger.bind(name=self.__class__.__name__)

        validate_config(config, [], "StooqClient config")

        self.base_url = config.get("base_url", "https://stooq.com/q/d/l/")
        self.timeout = config.get("timeout", 20)
        self.retry = config.get("retry", 3)
        self.retry_delay = config.get("retry_delay", 2)
        self.default_kline_count = config.get("default_kline_count", 200)

        # yfinance fallback 映射
        self.yahoo_symbols = config.get(
            "yahoo_symbols",
            {
                "xauusd": "GC=F",
                "xagusd": "SI=F",
            },
        )

        self.logger.info(f"Stooq client initialized with base_url: {self.base_url}")

    def _save_debug_response(self, symbol: str, text: str) -> Optional[Path]:
        try:
            debug_dir = Path("output/debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = debug_dir / f"stooq_raw_{symbol}_{timestamp}.txt"
            filepath.write_text(text, encoding="utf-8", errors="ignore")
            self.logger.warning(f"Saved raw Stooq response to: {filepath}")
            return filepath
        except Exception as e:
            self.logger.warning(f"Failed to save raw response for {symbol}: {e}")
            return None

    def _parse_csv_response(self, symbol: str, text: str) -> pd.DataFrame:
        raw_preview = text[:800].replace("\n", "\\n")
        self.logger.debug(f"Raw response preview for {symbol}: {raw_preview}")

        if not text or not text.strip():
            raise DataFetchError(f"Empty response from Stooq for symbol: {symbol}")

        if "No data" in text:
            raise DataFetchError(f"Stooq returned no data for symbol: {symbol}")

        lowered = text.lower()
        if "<html" in lowered or "<!doctype html" in lowered:
            self._save_debug_response(symbol, text)
            raise DataFetchError(
                f"Stooq returned HTML instead of CSV for symbol: {symbol}"
            )

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise DataFetchError(f"No non-empty lines in Stooq response for symbol: {symbol}")

        header_index = None
        for i, line in enumerate(lines):
            normalized = line.replace(" ", "").lower()
            if normalized.startswith("date,open,high,low,close"):
                header_index = i
                break

        if header_index is None:
            self._save_debug_response(symbol, text)
            raise DataFetchError(
                f"Could not find CSV header in Stooq response for symbol: {symbol}"
            )

        csv_text = "\n".join(lines[header_index:])

        try:
            df = pd.read_csv(
                StringIO(csv_text),
                sep=",",
                on_bad_lines="skip",
                engine="python",
            )
        except Exception as e:
            self._save_debug_response(symbol, text)
            raise DataFetchError(f"CSV parsing failed for symbol {symbol}: {e}")

        if df.empty:
            self._save_debug_response(symbol, text)
            raise DataFetchError(f"Parsed DataFrame is empty for symbol: {symbol}")

        required_columns = ["Date", "Open", "High", "Low", "Close"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            self._save_debug_response(symbol, text)
            raise DataFetchError(
                f"Missing columns in data for {symbol}: {missing_columns}. "
                f"Actual columns: {list(df.columns)}"
            )

        return df

    def _clean_ohlc_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            raise DataFetchError("Received empty DataFrame")

        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"])
            df = df.rename(columns={"Date": "timestamp"})
        elif "timestamp" not in df.columns:
            if df.index.name is not None:
                df = df.reset_index()
                first_col = df.columns[0]
                df[first_col] = pd.to_datetime(df[first_col], errors="coerce")
                df = df.dropna(subset=[first_col])
                df = df.rename(columns={first_col: "timestamp"})
            else:
                raise DataFetchError("Could not identify timestamp column")

        rename_map = {}
        for old, new in [
            ("Open", "open"),
            ("High", "high"),
            ("Low", "low"),
            ("Close", "close"),
            ("Volume", "volume"),
        ]:
            if old in df.columns:
                rename_map[old] = new
        df = df.rename(columns=rename_map)

        required = ["timestamp", "open", "high", "low", "close"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataFetchError(f"Missing OHLC columns after cleaning: {missing}")

        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close"])

        if "volume" not in df.columns:
            df["volume"] = 0
        else:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

        if df.empty:
            raise DataFetchError("All rows invalid after OHLC cleaning")

        df = df.set_index("timestamp")
        df.sort_index(inplace=True)

        return df[["open", "high", "low", "close", "volume"]]

    @with_retry(max_attempts=3, exceptions=(NetworkError, requests.RequestException))
    def _request_csv(self, symbol: str) -> pd.DataFrame:
        if not symbol or not isinstance(symbol, str):
            raise ValidationError(f"Invalid symbol: {symbol}")

        params = {
            "s": symbol.lower(),
            "i": "d",
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/csv,text/plain,application/octet-stream,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        try:
            self.logger.debug(f"Requesting Stooq data for symbol: {symbol}")
            response = requests.get(
                self.base_url,
                params=params,
                timeout=self.timeout,
                headers=headers,
            )
            response.raise_for_status()

            self.logger.debug(f"Stooq final URL for {symbol}: {response.url}")

            df = self._parse_csv_response(symbol, response.text)
            df = self._clean_ohlc_dataframe(df)

            self.logger.debug(f"Successfully fetched {len(df)} records from Stooq for {symbol}")
            return df

        except requests.RequestException as e:
            raise NetworkError(f"Network error fetching data for {symbol}: {e}")
        except (ValidationError, DataFetchError):
            raise
        except Exception as e:
            raise DataFetchError(f"Unexpected error fetching data for {symbol}: {e}")

    def _request_yfinance(self, symbol: str) -> pd.DataFrame:
        yahoo_symbol = self.yahoo_symbols.get(symbol.lower())
        if not yahoo_symbol:
            raise DataFetchError(f"No yfinance fallback symbol configured for: {symbol}")

        self.logger.warning(f"Falling back to yfinance for {symbol} -> {yahoo_symbol}")

        try:
            ticker = yf.Ticker(yahoo_symbol)
            hist = ticker.history(period="1y", interval="1d", auto_adjust=False)

            if hist is None or hist.empty:
                raise DataFetchError(f"yfinance returned no data for {symbol} ({yahoo_symbol})")

            hist = hist.reset_index()

            # 兼容 Date / Datetime
            if "Date" not in hist.columns:
                if "Datetime" in hist.columns:
                    hist = hist.rename(columns={"Datetime": "Date"})
                else:
                    first_col = hist.columns[0]
                    hist = hist.rename(columns={first_col: "Date"})

            df = self._clean_ohlc_dataframe(hist)
            self.logger.info(f"Successfully fetched {len(df)} records from yfinance for {symbol}")
            return df

        except Exception as e:
            raise DataFetchError(f"yfinance fallback failed for {symbol}: {e}")

    def _get_dataframe(self, symbol: str) -> pd.DataFrame:
        try:
            return self._request_csv(symbol)
        except Exception as stooq_error:
            self.logger.warning(f"Primary Stooq fetch failed for {symbol}: {stooq_error}")
            return self._request_yfinance(symbol)

    def _normalize_timeframe(self, timeframe: str) -> str:
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
            resampled["volume"] = df["volume"].resample(rule).sum()
            resampled.dropna(inplace=True)

            self.logger.debug(f"Resampled data to {timeframe}: {len(resampled)} records")
            return resampled

        except Exception as e:
            self.logger.error(f"Error resampling data to {timeframe}: {e}")
            return df

    def get_quote(self, symbol: str, region: str | None = None) -> Dict[str, Any]:
        if not symbol:
            raise ValidationError("Symbol cannot be empty")

        try:
            df = self._get_dataframe(symbol.lower())

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
                "volume": float(latest.get("volume", 0)),
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
        if not symbol:
            raise ValidationError("Symbol cannot be empty")

        if count is None:
            count = self.default_kline_count
        elif count <= 0:
            raise ValidationError(f"Count must be positive, got: {count}")

        try:
            df = self._get_dataframe(symbol.lower())
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
