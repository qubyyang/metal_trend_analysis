"""新浪财经数据源测试

重点覆盖 JSONP 剥离逻辑与异常路径 —— 这是该数据源最易碎的环节。
网络请求统一 mock，测试不依赖外部服务。
"""
from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from src.data_fetchers.sina_provider import SinaProvider
from src.utils.exceptions import DataFetchError, NetworkError


# 真实接口响应形态：防盗链注释 + JSONP 包装
SAMPLE_RESPONSE = (
    "/*<script>location.href='//sina.com';</script>*/\n"
    'x([{"date":"2026-09-01","open":"4300.0","high":"4350.0","low":"4280.0",'
    '"close":"4330.0","volume":"0"},'
    '{"date":"2026-09-02","open":"4331.0","high":"4397.0","low":"4282.0",'
    '"close":"4387.0","volume":"0"}])'
)


@pytest.fixture
def provider():
    return SinaProvider({})


def _mock_response(text: str) -> Mock:
    resp = Mock()
    resp.text = text
    resp.raise_for_status = Mock()
    return resp


class TestSymbolSupport:
    def test_supports_mapped_metals(self, provider):
        assert provider.supports("XAUUSD")
        assert provider.supports("XAGUSD")
        assert provider.supports("xauusd")  # 大小写不敏感

    def test_rejects_unmapped_symbol(self, provider):
        assert not provider.supports("AAPL")
        assert not provider.supports("")

    def test_resolve_unknown_symbol_raises(self, provider):
        with pytest.raises(DataFetchError):
            provider._resolve_symbol("AAPL")

    def test_name(self, provider):
        assert provider.name == "sina"


class TestJsonpStripping:
    def test_strips_comment_and_callback(self, provider):
        cleaned = provider._strip_jsonp(SAMPLE_RESPONSE)
        assert cleaned.startswith("[") and cleaned.endswith("]")

    def test_handles_plain_json_array(self, provider):
        assert provider._strip_jsonp('[{"a":1}]') == '[{"a":1}]'

    def test_raises_when_no_array_present(self, provider):
        with pytest.raises(DataFetchError):
            provider._strip_jsonp("not a json payload")


class TestFetchDaily:
    def test_parses_records_into_dataframe(self, provider):
        with patch("requests.get", return_value=_mock_response(SAMPLE_RESPONSE)):
            df = provider.fetch_daily("XAUUSD")

        assert len(df) == 2
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_end_to_end_standardization(self, provider):
        """经 get_kline 后应产出数值型、升序、无重复的标准 OHLCV"""
        with patch("requests.get", return_value=_mock_response(SAMPLE_RESPONSE)):
            df = provider.get_kline("XAUUSD", "1d", 10)

        assert df.index.is_monotonic_increasing
        assert df["close"].dtype.kind == "f"
        assert float(df["close"].iloc[-1]) == pytest.approx(4387.0)

    def test_quote_computes_change(self, provider):
        with patch("requests.get", return_value=_mock_response(SAMPLE_RESPONSE)):
            quote = provider.get_quote("XAUUSD")

        assert quote["source"] == "sina"
        assert quote["price"] == pytest.approx(4387.0)
        assert quote["change"] == pytest.approx(57.0)

    def test_network_error_wrapped(self, provider):
        with patch("requests.get", side_effect=requests.RequestException("timeout")):
            with pytest.raises(NetworkError):
                provider.fetch_daily("XAUUSD")

    def test_empty_payload_raises(self, provider):
        with patch("requests.get", return_value=_mock_response("x([])")):
            with pytest.raises(DataFetchError):
                provider.fetch_daily("XAUUSD")

    def test_missing_fields_raise(self, provider):
        with patch("requests.get", return_value=_mock_response('x([{"date":"2026-09-01"}])')):
            with pytest.raises(DataFetchError):
                provider.fetch_daily("XAUUSD")

    def test_malformed_json_raises(self, provider):
        with patch("requests.get", return_value=_mock_response("x([{broken}])")):
            with pytest.raises(DataFetchError):
                provider.fetch_daily("XAUUSD")
