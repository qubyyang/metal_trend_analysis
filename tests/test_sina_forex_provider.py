"""新浪外汇数据源（美元指数）测试 —— 全程 mock，不依赖网络"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.data_fetchers.sina_forex_provider import SinaForexProvider
from src.utils.exceptions import DataFetchError, NetworkError

_PREFIX = "/*<script>location.href='//sina.com';</script>*/\n"

# date, open, low, high, close
_SAMPLE = _PREFIX + (
    'x("2026-09-01,99.1000,98.9000,99.4000,99.2000,'
    "|2026-09-02,99.2000,99.0000,99.5000,99.3000,"
    '|2026-09-03,99.3000,99.1000,99.6000,99.1500")'
)

_EMPTY = _PREFIX + 'x({"msg":"data is empty"});'


def _mock_response(text: str) -> Mock:
    resp = Mock()
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


@pytest.fixture
def provider():
    return SinaForexProvider()


class TestSupports:
    def test_supports_dxy_aliases(self, provider):
        assert provider.supports("DXY") is True
        assert provider.supports("USDIDX") is True
        assert provider.supports("dxy") is True

    def test_rejects_metals(self, provider):
        """贵金属应由 SinaProvider 处理，本源不得抢占"""
        assert provider.supports("XAUUSD") is False
        assert provider.supports("") is False

    def test_name(self, provider):
        assert provider.name == "sina_forex"


class TestExtractPayload:
    def test_strips_prefix_and_wrapper(self, provider):
        payload = provider._extract_payload(_SAMPLE)

        assert payload.startswith("2026-09-01")
        assert "<script>" not in payload

    def test_empty_object_response_raises(self, provider):
        with pytest.raises(DataFetchError):
            provider._extract_payload(_EMPTY)

    def test_garbage_raises(self, provider):
        with pytest.raises(DataFetchError):
            provider._extract_payload("not a jsonp response")


class TestFetchDaily:
    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_field_order_is_date_open_low_high_close(self, mock_get, provider):
        """关键回归：第 2 列是 low、第 3 列才是 high，顺序不得写反"""
        mock_get.return_value = _mock_response(_SAMPLE)
        df = provider.fetch_daily("DXY")

        assert len(df) == 3
        last = df.iloc[-1]
        assert last["open"] == pytest.approx(99.30)
        assert last["low"] == pytest.approx(99.10)
        assert last["high"] == pytest.approx(99.60)
        assert last["close"] == pytest.approx(99.15)

    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_ohlc_invariant_holds(self, mock_get, provider):
        """解析后必须满足 low <= min(open,close) <= max(open,close) <= high"""
        mock_get.return_value = _mock_response(_SAMPLE)
        df = provider.fetch_daily("DXY")

        assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
        assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()

    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_index_is_sorted_datetime(self, mock_get, provider):
        mock_get.return_value = _mock_response(_SAMPLE)
        df = provider.fetch_daily("DXY")

        assert df.index.name == "timestamp"
        assert list(df.index) == sorted(df.index)

    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_malformed_rows_skipped(self, mock_get, provider):
        """字段数不足的行应被跳过而非报错"""
        text = _PREFIX + 'x("2026-09-01,99.1,98.9,99.4,99.2|BROKEN|2026-09-02,99.2,99.0,99.5,99.3")'
        mock_get.return_value = _mock_response(text)
        df = provider.fetch_daily("DXY")

        assert len(df) == 2

    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_network_error_wrapped(self, mock_get, provider):
        import requests as _requests

        mock_get.side_effect = _requests.Timeout("timeout")
        with pytest.raises(NetworkError):
            provider.fetch_daily("DXY")

    def test_unsupported_symbol_raises(self, provider):
        with pytest.raises(DataFetchError):
            provider.fetch_daily("XAUUSD")


class TestStandardizeIntegration:
    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_get_quote_change_direction(self, mock_get, provider):
        mock_get.return_value = _mock_response(_SAMPLE)
        quote = provider.get_quote("DXY")

        assert quote["price"] == pytest.approx(99.15)
        # 前一日收 99.30 -> 当前 99.15，应为下跌
        assert quote["change"] < 0
        assert quote["source"] == "sina_forex"

    @patch("src.data_fetchers.sina_forex_provider.requests.get")
    def test_volume_column_filled(self, mock_get, provider):
        """外汇接口无成交量，标准化后应补 0 而非缺列"""
        mock_get.return_value = _mock_response(_SAMPLE)
        df = provider.get_kline("DXY")

        assert "volume" in df.columns
        assert (df["volume"] == 0).all()
