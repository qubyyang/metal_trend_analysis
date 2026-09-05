"""
行情数据聚合客户端

职责：
1. 按优先级调度多个数据源，主源失败时自动降级到备源
2. 本地磁盘缓存，在全部数据源不可用时提供陈旧数据兜底
3. 对外提供与原 StooqClient 兼容的 get_quote / get_kline 接口
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

from ..utils.exceptions import DataFetchError, ValidationError
from .base_provider import BaseDataProvider
from .sina_provider import SinaProvider
from .stooq_provider import StooqProvider
from .yahoo_provider import YahooProvider

# 数据源注册表
PROVIDER_REGISTRY = {
    "sina": SinaProvider,
    "stooq": StooqProvider,
    "yahoo": YahooProvider,
}

# 新浪置于首位：国内直连稳定，且 Stooq 已启用 JS 反爬、Yahoo 对部分地区返回 403
DEFAULT_PROVIDER_ORDER = ["sina", "stooq", "yahoo"]


class MarketDataClient:
    """多数据源行情客户端，支持自动降级与缓存兜底"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        self.cache_enabled = self.config.get("cache_enabled", True)
        self.cache_ttl = self.config.get("cache_ttl", 3600)
        self.cache_dir = Path(self.config.get("cache_dir", "data/cache"))
        self.default_kline_count = self.config.get("default_kline_count", 200)
        # 全部数据源失败时，是否允许使用过期缓存
        self.allow_stale_cache = self.config.get("allow_stale_cache", True)

        self.providers: List[BaseDataProvider] = self._build_providers()
        if not self.providers:
            raise ValidationError("未配置任何可用的行情数据源")

        self.logger.info(
            f"行情客户端初始化完成，数据源优先级: {[p.name for p in self.providers]}"
        )

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _build_providers(self) -> List[BaseDataProvider]:
        order = self.config.get("providers") or DEFAULT_PROVIDER_ORDER
        providers = []

        for name in order:
            provider_cls = PROVIDER_REGISTRY.get(name)
            if provider_cls is None:
                self.logger.warning(f"未知数据源，已跳过: {name}")
                continue

            provider_config = {
                **{k: v for k, v in self.config.items() if k in ("timeout", "default_kline_count")},
                **self.config.get(name, {}),
            }

            try:
                providers.append(provider_cls(provider_config))
            except Exception as e:
                self.logger.error(f"数据源 {name} 初始化失败，已跳过: {e}")

        return providers

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------
    def _cache_path(self, symbol: str) -> Path:
        key = hashlib.md5(symbol.upper().encode("utf-8")).hexdigest()[:12]
        return self.cache_dir / f"{symbol.upper()}_{key}_daily.csv"

    def _cache_meta_path(self, symbol: str) -> Path:
        """缓存元数据路径（记录数据来源，与 CSV 数据分离存放）"""
        return self._cache_path(symbol).with_suffix(".meta")

    def _read_cache_source(self, symbol: str) -> str:
        """读取缓存对应的原始数据源名称"""
        try:
            meta = self._cache_meta_path(symbol)
            if meta.exists():
                name = meta.read_text(encoding="utf-8").strip()
                if name:
                    return name
        except Exception:  # pragma: no cover - 元数据缺失不应影响主流程
            pass
        return "cache"

    def _read_cache(self, symbol: str, allow_stale: bool = False) -> Optional[pd.DataFrame]:
        if not self.cache_enabled:
            return None

        path = self._cache_path(symbol)
        if not path.exists():
            return None

        age = time.time() - path.stat().st_mtime
        if age > self.cache_ttl and not allow_stale:
            return None

        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            if df.empty:
                return None
            if age > self.cache_ttl:
                self.logger.warning(
                    f"{symbol} 使用过期缓存兜底（已过期 {age / 3600:.1f} 小时）"
                )
            return df
        except Exception as e:
            self.logger.warning(f"{symbol} 缓存读取失败: {e}")
            return None

    def _write_cache(self, symbol: str, df: pd.DataFrame, source: str = "") -> None:
        if not self.cache_enabled or df.empty:
            return

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(self._cache_path(symbol))
            if source:
                self._cache_meta_path(symbol).write_text(source, encoding="utf-8")
        except Exception as e:
            self.logger.warning(f"{symbol} 缓存写入失败: {e}")

    # ------------------------------------------------------------------
    # 核心调度
    # ------------------------------------------------------------------
    def fetch_daily(self, symbol: str, use_cache: bool = True) -> pd.DataFrame:
        """获取日线数据，按优先级尝试各数据源，失败则回退缓存

        Returns:
            标准化后的日线 DataFrame

        Raises:
            DataFetchError: 所有数据源与缓存均不可用
        """
        if not symbol:
            raise ValidationError("symbol 不能为空")

        if use_cache:
            cached = self._read_cache(symbol)
            if cached is not None:
                self.logger.debug(f"{symbol} 命中有效缓存")
                self._last_source = self._read_cache_source(symbol)
                return cached

        errors: List[str] = []

        for provider in self.providers:
            if not provider.supports(symbol):
                continue

            try:
                raw = provider.fetch_daily(symbol)
                df = provider._standardize(raw, symbol)
                self.logger.info(
                    f"{symbol} 数据获取成功，来源: {provider.name}（{len(df)} 条）"
                )
                self._write_cache(symbol, df, provider.name)
                self._last_source = provider.name
                return df
            except Exception as e:
                errors.append(f"{provider.name}: {e}")
                self.logger.warning(f"数据源 {provider.name} 获取 {symbol} 失败: {e}")

        # 全部数据源失败，尝试过期缓存兜底
        if self.allow_stale_cache:
            stale = self._read_cache(symbol, allow_stale=True)
            if stale is not None:
                self._last_source = "stale_cache"
                return stale

        raise DataFetchError(
            f"{symbol} 所有数据源均获取失败: " + "; ".join(errors)
        )

    # ------------------------------------------------------------------
    # 对外接口（兼容原 StooqClient）
    # ------------------------------------------------------------------
    def get_kline(
        self,
        symbol: str,
        timeframe: str = "1d",
        count: Optional[int] = None,
        region: str | None = None,
    ) -> pd.DataFrame:
        """获取 K 线数据（region 参数仅为向后兼容，不参与逻辑）"""
        if count is None:
            count = self.default_kline_count
        elif count <= 0:
            raise ValidationError(f"count 必须为正数，当前值: {count}")

        df = self.fetch_daily(symbol)
        df = self.providers[0].resample(df, timeframe)

        if len(df) > count:
            df = df.tail(count)

        return df

    def get_quote(self, symbol: str, region: str | None = None) -> Dict[str, Any]:
        """获取最新报价（基于日线收盘）"""
        df = self.fetch_daily(symbol)

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
            "source": getattr(self, "_last_source", "unknown"),
            "bar_time": df.index[-1].isoformat(),
            "timestamp": datetime.now().isoformat(),
        }

    def save_raw_data(
        self, df: pd.DataFrame, symbol: str, timeframe: str
    ) -> Optional[Path]:
        """保存原始数据快照"""
        if df is None or df.empty:
            self.logger.warning(f"{symbol} 无数据可保存")
            return None

        try:
            output_dir = Path("data/raw")
            output_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = output_dir / f"{symbol}_{timeframe}_{timestamp}.csv"
            df.to_csv(filepath)
            self.logger.info(f"原始数据已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"{symbol} 原始数据保存失败: {e}")
            return None
