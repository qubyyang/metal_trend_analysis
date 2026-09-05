"""跨品种联动分析测试"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analyzers.cross_asset import CrossAssetAnalyzer


def _make_df(values, start="2024-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    values = np.asarray(values, dtype=float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values * 1.01,
            "low": values * 0.99,
            "close": values,
            "volume": 0,
        },
        index=idx,
    )


@pytest.fixture
def analyzer():
    return CrossAssetAnalyzer({"correlation_window": 20, "percentile_window": 100})


class TestRatios:
    def test_ratio_direction_is_numerator_over_denominator(self, analyzer):
        """金银比必须是 金/银，不能算反"""
        data = {
            "XAUUSD": _make_df([2000.0] * 50),
            "XAGUSD": _make_df([25.0] * 50),
        }
        ratios = {r["key"]: r for r in analyzer.compute_ratios(data)}

        assert "gold_silver" in ratios
        assert ratios["gold_silver"]["value"] == pytest.approx(80.0)
        assert ratios["gold_silver"]["pair"] == "XAUUSD/XAGUSD"

    def test_missing_symbol_skips_only_that_ratio(self, analyzer):
        """缺失辅助品种时只跳过相关比价，其余照常输出"""
        data = {
            "XAUUSD": _make_df([2000.0] * 50),
            "XAGUSD": _make_df([25.0] * 50),
            # 无 XPTUSD / HGUSD
        }
        keys = {r["key"] for r in analyzer.compute_ratios(data)}

        assert keys == {"gold_silver"}

    def test_misaligned_dates_are_inner_joined(self, analyzer):
        """交易日不一致时按日期内连接，不产生错位比价"""
        gold = _make_df([2000.0] * 30, start="2024-01-01")
        silver = _make_df([25.0] * 30, start="2024-01-11")
        ratios = analyzer.compute_ratios({"XAUUSD": gold, "XAGUSD": silver})

        assert len(ratios) == 1
        # 重叠区间为 20 天
        assert ratios[0]["sample_size"] == 20
        assert ratios[0]["value"] == pytest.approx(80.0)

    def test_zero_denominator_filtered(self, analyzer):
        """分母为零的样本必须被剔除，不能产生 inf"""
        data = {
            "XAUUSD": _make_df([2000.0] * 30),
            "XAGUSD": _make_df([0.0] * 10 + [25.0] * 20),
        }
        ratios = analyzer.compute_ratios(data)

        assert len(ratios) == 1
        assert np.isfinite(ratios[0]["value"])

    def test_percentile_reflects_position_in_window(self, analyzer):
        """当前值为窗口最大时，分位应接近 100%"""
        rising = np.linspace(1000, 2000, 60)
        data = {"XAUUSD": _make_df(rising), "XAGUSD": _make_df([25.0] * 60)}
        ratios = analyzer.compute_ratios(data)

        assert ratios[0]["percentile"] == pytest.approx(100.0)


class TestCorrelations:
    def test_perfectly_correlated_series(self, analyzer):
        """完全同步的收益率序列相关性应接近 +1"""
        rng = np.random.default_rng(42)
        base = 2000 * np.exp(np.cumsum(rng.normal(0, 0.01, 120)))
        data = {"XAUUSD": _make_df(base), "XAGUSD": _make_df(base * 0.0125)}

        corrs = {c["pair"]: c for c in analyzer.compute_correlations(data)}
        assert corrs["XAUUSD~XAGUSD"]["correlation"] == pytest.approx(1.0, abs=1e-6)

    def test_correlation_uses_returns_not_prices(self, analyzer):
        """两条独立随机游走的价格序列会有伪高相关，但收益率相关应接近 0"""
        rng = np.random.default_rng(7)
        a = 2000 * np.exp(np.cumsum(rng.normal(0.002, 0.01, 400)))
        b = 100 * np.exp(np.cumsum(rng.normal(0.002, 0.01, 400)))

        analyzer.corr_window = 200
        corrs = {c["pair"]: c for c in analyzer.compute_correlations(
            {"XAUUSD": _make_df(a), "XAGUSD": _make_df(b)}
        )}
        # 若误用价格计算，共同漂移会把相关拉到 0.9 以上
        assert abs(corrs["XAUUSD~XAGUSD"]["correlation"]) < 0.3

    def test_insufficient_overlap_skipped(self, analyzer):
        """重叠样本不足时跳过，而非报错"""
        data = {"XAUUSD": _make_df([2000.0] * 10), "XAGUSD": _make_df([25.0] * 10)}
        assert analyzer.compute_correlations(data) == []

    def test_sign_flip_detected(self, analyzer):
        """黄金与美元指数出现正相关时应标记方向翻转"""
        rng = np.random.default_rng(3)
        base = np.cumsum(rng.normal(0, 0.01, 150))
        gold = 2000 * np.exp(base)
        dxy = 100 * np.exp(base)  # 人为构造同向

        corrs = {c["pair"]: c for c in analyzer.compute_correlations(
            {"XAUUSD": _make_df(gold), "DXY": _make_df(dxy)}
        )}
        assert corrs["XAUUSD~DXY"]["sign_flipped"] is True


class TestAnalyzeIntegration:
    def test_empty_input_returns_unavailable(self, analyzer):
        result = analyzer.analyze({})

        assert result["available"] is False
        assert result["ratios"] == []
        assert result["correlations"] == []

    def test_partial_data_does_not_raise(self, analyzer):
        """只有单一品种时不应抛异常"""
        result = analyzer.analyze({"XAUUSD": _make_df([2000.0] * 50)})

        assert result["available"] is False
        assert result["alerts"] == []

    def test_full_result_shape(self, analyzer):
        rng = np.random.default_rng(11)
        n = 150
        gold = 2000 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        data = {
            "XAUUSD": _make_df(gold),
            "XAGUSD": _make_df(gold / 80),
            "XPTUSD": _make_df(gold / 2.2),
            "HGUSD": _make_df(gold / 6.5),
        }
        result = analyzer.analyze(data)

        assert result["available"] is True
        assert len(result["ratios"]) == 3
        assert isinstance(result["alerts"], list)
        for r in result["ratios"]:
            assert np.isfinite(r["value"])
            assert 0 <= r["percentile"] <= 100
