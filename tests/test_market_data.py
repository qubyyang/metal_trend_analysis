"""行情数据源降级与缓存测试"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.data_fetchers.base_provider import BaseDataProvider
from src.data_fetchers.market_data import MarketDataClient
from src.data_fetchers.stooq_provider import StooqProvider
from src.data_fetchers.yahoo_provider import YahooProvider
from src.utils.exceptions import DataFetchError, ValidationError


def make_daily(n=60, start_price=2000.0):
    index = pd.date_range(start="2024-01-01", periods=n, freq="D")
    closes = start_price + np.arange(n, dtype=float)
    return pd.DataFrame({
        "open": closes - 1, "high": closes + 2,
        "low": closes - 2, "close": closes, "volume": 100,
    }, index=index)


class FakeProvider(BaseDataProvider):
    """可控的测试数据源"""

    def __init__(self, name, df=None, error=None):
        super().__init__({})
        self._name = name
        self._df = df
        self._error = error
        self.call_count = 0

    @property
    def name(self):
        return self._name

    def fetch_daily(self, symbol):
        self.call_count += 1
        if self._error:
            raise self._error
        return self._df


@pytest.fixture
def client(tmp_path):
    c = MarketDataClient({"cache_dir": str(tmp_path / "cache"), "cache_ttl": 3600})
    return c


class TestBaseProvider:
    def test_standardize_fills_missing_volume(self):
        provider = FakeProvider("t", make_daily())
        df = make_daily().drop(columns=["volume"])
        result = provider._standardize(df, "XAUUSD")

        assert "volume" in result.columns
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]

    def test_standardize_rejects_missing_ohlc(self):
        provider = FakeProvider("t")
        with pytest.raises(DataFetchError):
            provider._standardize(pd.DataFrame({"close": [1.0]}), "XAUUSD")

    def test_standardize_rejects_empty(self):
        provider = FakeProvider("t")
        with pytest.raises(DataFetchError):
            provider._standardize(pd.DataFrame(), "XAUUSD")

    def test_standardize_sorts_and_dedups(self):
        provider = FakeProvider("t")
        df = make_daily(5)
        shuffled = pd.concat([df.iloc[[3]], df.iloc[[1]], df.iloc[[3]]])
        result = provider._standardize(shuffled, "XAUUSD")

        assert result.index.is_monotonic_increasing
        assert not result.index.duplicated().any()

    @pytest.mark.parametrize("raw,expected", [
        ("1d", "1d"), ("day", "1d"), ("1w", "1w"), ("week", "1w"),
        ("1m", "1m"), ("month", "1m"), ("unknown", "1d"), ("", "1d"), (None, "1d"),
    ])
    def test_normalize_timeframe(self, raw, expected):
        assert BaseDataProvider._normalize_timeframe(raw) == expected

    def test_weekly_resample_aggregates_correctly(self):
        provider = FakeProvider("t")
        df = provider._standardize(make_daily(28), "XAUUSD")
        weekly = provider.resample(df, "1w")

        assert len(weekly) < len(df)
        assert (weekly["high"] >= weekly["low"]).all()
        assert (weekly["high"] >= weekly["close"]).all()


class TestFailover:
    def test_primary_source_used_when_healthy(self, client):
        primary = FakeProvider("primary", make_daily())
        backup = FakeProvider("backup", make_daily())
        client.providers = [primary, backup]

        df = client.fetch_daily("XAUUSD")

        assert not df.empty
        assert primary.call_count == 1
        assert backup.call_count == 0, "主源正常时不应调用备源"

    def test_falls_back_to_backup_on_primary_failure(self, client):
        primary = FakeProvider("primary", error=DataFetchError("主源宕机"))
        backup = FakeProvider("backup", make_daily())
        client.providers = [primary, backup]

        df = client.fetch_daily("XAUUSD")

        assert not df.empty
        assert backup.call_count == 1
        assert client._last_source == "backup"

    def test_raises_when_all_sources_fail(self, client):
        client.providers = [
            FakeProvider("a", error=DataFetchError("A 挂了")),
            FakeProvider("b", error=DataFetchError("B 挂了")),
        ]
        client.allow_stale_cache = False

        with pytest.raises(DataFetchError) as exc:
            client.fetch_daily("XAUUSD")

        assert "所有数据源均获取失败" in str(exc.value)

    def test_stale_cache_used_as_last_resort(self, client):
        # 先用健康数据源写入缓存
        client.providers = [FakeProvider("primary", make_daily())]
        client.fetch_daily("XAUUSD")

        # 数据源全挂，且缓存已过期
        client.providers = [FakeProvider("primary", error=DataFetchError("宕机"))]
        client.cache_ttl = -1

        df = client.fetch_daily("XAUUSD", use_cache=False)

        assert not df.empty
        assert client._last_source == "stale_cache"

    def test_empty_symbol_rejected(self, client):
        with pytest.raises(ValidationError):
            client.fetch_daily("")


class TestCache:
    def test_cache_avoids_second_network_call(self, client):
        provider = FakeProvider("primary", make_daily())
        client.providers = [provider]

        client.fetch_daily("XAUUSD")
        client.fetch_daily("XAUUSD")

        assert provider.call_count == 1, "第二次调用应命中缓存"

    def test_use_cache_false_forces_refetch(self, client):
        provider = FakeProvider("primary", make_daily())
        client.providers = [provider]

        client.fetch_daily("XAUUSD")
        client.fetch_daily("XAUUSD", use_cache=False)

        assert provider.call_count == 2

    def test_expired_cache_triggers_refetch(self, client):
        provider = FakeProvider("primary", make_daily())
        client.providers = [provider]

        client.fetch_daily("XAUUSD")
        client.cache_ttl = -1
        client.fetch_daily("XAUUSD")

        assert provider.call_count == 2


class TestPublicApi:
    def test_get_quote_shape(self, client):
        client.providers = [FakeProvider("primary", make_daily())]
        quote = client.get_quote("XAUUSD")

        for key in ["symbol", "price", "change", "change_percent", "source", "bar_time"]:
            assert key in quote
        assert quote["source"] == "primary"
        assert quote["price"] > 0

    def test_get_quote_change_direction(self, client):
        client.providers = [FakeProvider("primary", make_daily())]
        quote = client.get_quote("XAUUSD")

        # 构造数据为单调上涨，最新一根应为正变动
        assert quote["change"] > 0
        assert quote["change_percent"] > 0

    def test_get_kline_respects_count(self, client):
        client.providers = [FakeProvider("primary", make_daily(200))]
        df = client.get_kline("XAUUSD", "1d", count=30)

        assert len(df) == 30

    def test_get_kline_rejects_bad_count(self, client):
        client.providers = [FakeProvider("primary", make_daily())]
        with pytest.raises(ValidationError):
            client.get_kline("XAUUSD", "1d", count=0)

    def test_save_raw_data_handles_empty(self, client):
        assert client.save_raw_data(pd.DataFrame(), "XAUUSD", "1d") is None


class TestSymbolMapping:
    def test_stooq_maps_known_symbols(self):
        provider = StooqProvider({})
        assert provider._resolve_symbol("XAUUSD") == "xauusd"
        assert provider._resolve_symbol("XAGUSD") == "xagusd"

    def test_yahoo_maps_to_futures_contracts(self):
        provider = YahooProvider({})
        assert provider._resolve_symbol("XAUUSD") == "GC=F"
        assert provider._resolve_symbol("XAGUSD") == "SI=F"

    def test_unknown_symbol_passthrough(self):
        assert YahooProvider({})._resolve_symbol("AAPL") == "AAPL"


class TestYahooParsing:
    def test_parses_chart_payload(self):
        provider = YahooProvider({})
        payload = {"chart": {"error": None, "result": [{
            "timestamp": [1704067200, 1704153600],
            "indicators": {"quote": [{
                "open": [2000.0, 2010.0], "high": [2020.0, 2030.0],
                "low": [1990.0, 2000.0], "close": [2010.0, 2025.0],
                "volume": [100, 120],
            }]},
        }]}}

        with patch("src.data_fetchers.yahoo_provider.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: payload, raise_for_status=lambda: None
            )
            df = provider.fetch_daily("XAUUSD")

        assert len(df) == 2
        assert df["close"].iloc[-1] == 2025.0

    def test_api_error_raises(self):
        provider = YahooProvider({})
        payload = {"chart": {"error": {"code": "Not Found"}, "result": None}}

        with patch("src.data_fetchers.yahoo_provider.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, json=lambda: payload, raise_for_status=lambda: None
            )
            with pytest.raises(DataFetchError):
                provider.fetch_daily("BADSYM")


class TestStooqParsing:
    def test_parses_csv(self):
        provider = StooqProvider({})
        csv = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01,2000,2020,1990,2010,0\n"
            "2024-01-02,2010,2030,2000,2025,0\n"
        )

        with patch("src.data_fetchers.stooq_provider.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text=csv, raise_for_status=lambda: None
            )
            df = provider.fetch_daily("XAUUSD")

        assert len(df) == 2
        assert df["close"].iloc[-1] == 2025

    def test_no_data_response_raises(self):
        provider = StooqProvider({})

        with patch("src.data_fetchers.stooq_provider.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200, text="No data", raise_for_status=lambda: None
            )
            with pytest.raises(DataFetchError):
                provider.fetch_daily("BADSYM")


class TestLegacyConfigCompatibility:
    """存量配置兼容性

    新增的专用数据源必须对旧 config.yaml 可见，
    否则升级后美元指数等新品种会静默降级失败。
    """

    def test_sina_forex_inserted_before_generic_providers(self):
        """旧配置未列出 sina_forex 时，应补齐到通用源之前"""
        client = MarketDataClient({
            "providers": ["sina", "stooq", "yahoo"],
            "cache_enabled": False,
        })
        names = [p.name for p in client.providers]

        assert names == ["sina", "sina_forex", "stooq", "yahoo"]
        # 用户显式配置的相对顺序未被打乱
        assert names.index("sina") < names.index("stooq") < names.index("yahoo")

    def test_no_duplicate_when_already_configured(self):
        """已显式配置时不得重复添加"""
        client = MarketDataClient({
            "providers": ["sina", "sina_forex"],
            "cache_enabled": False,
        })
        names = [p.name for p in client.providers]

        assert names.count("sina_forex") == 1

    def test_dxy_tried_by_forex_provider_first(self):
        """DXY 应优先落到 sina_forex，避免通用源做无谓的失败请求

        stooq / yahoo 的 supports() 恒为 True，若排在前面会先请求再失败，
        白白付出两次网络往返。
        """
        client = MarketDataClient({
            "providers": ["sina", "stooq", "yahoo"],
            "cache_enabled": False,
        })
        supporting = [p.name for p in client.providers if p.supports("DXY")]

        assert supporting[0] == "sina_forex"

    def test_metals_not_captured_by_forex_provider(self):
        """贵金属不得被外汇源抢占"""
        client = MarketDataClient({"cache_enabled": False})
        supporting = [p.name for p in client.providers if p.supports("XAUUSD")]

        assert supporting[0] == "sina"
        assert "sina_forex" not in supporting


class TestLegacyConfigCompatibility:
    """存量配置兼容性

    新增的专用数据源必须对旧 config.yaml 可见，
    否则升级后美元指数等新品种会静默降级失败。
    """

    def test_sina_forex_inserted_before_generic_providers(self):
        """旧配置未列出 sina_forex 时，应补齐到通用源之前"""
        client = MarketDataClient({
            "providers": ["sina", "stooq", "yahoo"],
            "cache_enabled": False,
        })
        names = [p.name for p in client.providers]

        assert names == ["sina", "sina_forex", "stooq", "yahoo"]
        # 用户显式配置的相对顺序未被打乱
        assert names.index("sina") < names.index("stooq") < names.index("yahoo")

    def test_no_duplicate_when_already_configured(self):
        """已显式配置时不得重复添加"""
        client = MarketDataClient({
            "providers": ["sina", "sina_forex"],
            "cache_enabled": False,
        })
        names = [p.name for p in client.providers]

        assert names.count("sina_forex") == 1

    def test_dxy_tried_by_forex_provider_first(self):
        """DXY 应优先落到 sina_forex，避免通用源做无谓的失败请求

        stooq / yahoo 的 supports() 恒为 True，若排在前面会先请求再失败，
        白白付出两次网络往返。
        """
        client = MarketDataClient({
            "providers": ["sina", "stooq", "yahoo"],
            "cache_enabled": False,
        })
        supporting = [p.name for p in client.providers if p.supports("DXY")]

        assert supporting[0] == "sina_forex"

    def test_metals_not_captured_by_forex_provider(self):
        """贵金属不得被外汇源抢占"""
        client = MarketDataClient({"cache_enabled": False})
        supporting = [p.name for p in client.providers if p.supports("XAUUSD")]

        assert supporting[0] == "sina"
        assert "sina_forex" not in supporting
