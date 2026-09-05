"""技术指标计算与趋势研判测试"""
import numpy as np
import pandas as pd
import pytest

from src.analyzers.technical import TechnicalAnalyzer
from src.utils.exceptions import ValidationError


@pytest.fixture
def analyzer(indicator_config):
    return TechnicalAnalyzer(indicator_config)


class TestIndicatorCalculation:
    def test_calculate_all_indicators_produces_expected_columns(self, analyzer, uptrend_df):
        result = analyzer.calculate_all_indicators(uptrend_df)

        for col in ["MA5", "MA20", "MACD_DIF", "MACD_DEA", "MACD_HIST",
                    "RSI", "BB_UPPER", "BB_MIDDLE", "BB_LOWER"]:
            assert col in result.columns, f"缺少指标列: {col}"

        assert len(result) == len(uptrend_df)

    def test_rsi_stays_within_bounds(self, analyzer, oscillating_df):
        """RSI 必须落在 [0, 100]，且不得出现 inf —— 旧实现存在除零缺陷"""
        rsi = analyzer.calculate_rsi(oscillating_df).dropna()

        assert not rsi.empty
        assert np.isfinite(rsi).all(), "RSI 出现 inf/NaN"
        assert (rsi >= 0).all() and (rsi <= 100).all()

    def test_rsi_high_in_uptrend(self, analyzer, uptrend_df):
        """单边上涨时 RSI 应处于高位"""
        rsi = analyzer.calculate_rsi(uptrend_df).dropna()
        assert rsi.iloc[-1] > 70

    def test_rsi_low_in_downtrend(self, analyzer, downtrend_df):
        rsi = analyzer.calculate_rsi(downtrend_df).dropna()
        assert rsi.iloc[-1] < 30

    def test_rsi_no_division_by_zero_on_monotonic_data(self, analyzer, make_ohlc):
        """全程上涨（无下跌）时不得因除零产生 inf"""
        df = make_ohlc(np.arange(100, 160, dtype=float))
        rsi = analyzer.calculate_rsi(df).dropna()

        assert np.isfinite(rsi).all()
        assert (rsi <= 100).all()

    def test_bollinger_band_ordering(self, analyzer, oscillating_df):
        bb = analyzer.calculate_bollinger(oscillating_df)
        valid = bb["upper"].notna() & bb["lower"].notna()

        assert valid.any()
        assert (bb["upper"][valid] >= bb["middle"][valid]).all()
        assert (bb["middle"][valid] >= bb["lower"][valid]).all()

    def test_macd_hist_matches_dif_dea(self, analyzer, uptrend_df):
        macd = analyzer.calculate_macd(uptrend_df)
        expected = (macd["dif"] - macd["dea"]) * 2

        pd.testing.assert_series_equal(
            macd["hist"].dropna(), expected.dropna(), check_names=False
        )

    def test_atr_is_non_negative(self, analyzer, oscillating_df):
        atr = analyzer.calculate_atr(oscillating_df).dropna()

        assert not atr.empty
        assert (atr >= 0).all()

    def test_ma_periods_respect_config(self, analyzer, uptrend_df):
        ma = analyzer.calculate_ma(uptrend_df)
        assert set(ma.keys()) == {5, 10, 20, 60}


class TestValidation:
    def test_empty_dataframe_rejected(self, analyzer):
        with pytest.raises(ValidationError):
            analyzer.calculate_all_indicators(pd.DataFrame())

    def test_missing_columns_rejected(self, analyzer):
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        with pytest.raises(ValidationError):
            analyzer.calculate_all_indicators(df)

    def test_non_numeric_columns_rejected(self, analyzer):
        df = pd.DataFrame({
            "open": ["a", "b"], "high": ["a", "b"],
            "low": ["a", "b"], "close": ["a", "b"],
        })
        with pytest.raises(ValidationError):
            analyzer.calculate_all_indicators(df)


class TestTrendAnalysis:
    def test_uptrend_detected_as_bullish(self, analyzer, uptrend_df):
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(uptrend_df))
        assert result["trend"] == "bullish"

    def test_downtrend_detected_as_bearish(self, analyzer, downtrend_df):
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(downtrend_df))
        assert result["trend"] == "bearish"

    def test_downstream_fields_present(self, analyzer, uptrend_df):
        """generator.py 与 llm/analyzer.py 依赖这些字段，缺失会导致报告缺块"""
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(uptrend_df))

        for field in ["trend", "ma_trend", "ma_alignment", "macd_signal",
                      "rsi", "rsi_signal", "bb_position", "signals_count"]:
            assert field in result, f"缺少下游依赖字段: {field}"

    def test_ma_trend_is_mapping_of_values(self, analyzer, uptrend_df):
        """ma_trend 需为 {MA5: 数值} 结构供报告渲染"""
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(uptrend_df))
        ma_trend = result["ma_trend"]

        assert isinstance(ma_trend, dict) and ma_trend
        for key, value in ma_trend.items():
            assert key.startswith("MA")
            assert isinstance(value, float)

    def test_ma_alignment_true_in_uptrend(self, analyzer, uptrend_df):
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(uptrend_df))
        assert result["ma_alignment"] is True

    def test_ma_alignment_false_in_downtrend(self, analyzer, downtrend_df):
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(downtrend_df))
        assert result["ma_alignment"] is False

    def test_bb_position_valid_value(self, analyzer, oscillating_df):
        result = analyzer.get_trend_analysis(analyzer.calculate_all_indicators(oscillating_df))
        assert result["bb_position"] in {"above_upper", "below_lower", "middle"}


class TestSupportResistance:
    def test_levels_are_sane(self, analyzer, oscillating_df):
        support, resistance = analyzer.identify_support_resistance(oscillating_df)

        assert isinstance(support, list) and isinstance(resistance, list)
        for level in support + resistance:
            assert isinstance(level, float) and level > 0

    def test_insufficient_data_returns_empty(self, analyzer, make_ohlc):
        df = make_ohlc([2000.0, 2010.0, 2005.0])
        support, resistance = analyzer.identify_support_resistance(df)

        assert support == [] and resistance == []

    def test_support_below_and_resistance_above_current_price(
        self, analyzer, oscillating_df
    ):
        """回归测试：支撑必须低于现价，阻力必须高于现价。

        历史缺陷：摆动低点被无条件归为支撑，导致报告出现
        「第一支撑 $4500 > 现价 $4436」这类自相矛盾的点位。
        """
        support, resistance = analyzer.identify_support_resistance(oscillating_df)
        current_price = float(oscillating_df["close"].iloc[-1])

        for level in support:
            assert level < current_price, (
                f"支撑位 {level} 不应高于现价 {current_price}"
            )
        for level in resistance:
            assert level > current_price, (
                f"阻力位 {level} 不应低于现价 {current_price}"
            )

    def test_levels_ordered_by_proximity_to_price(self, analyzer, oscillating_df):
        """第一支撑应最贴近现价（降序），第一阻力应最贴近现价（升序）"""
        support, resistance = analyzer.identify_support_resistance(oscillating_df)

        assert support == sorted(support, reverse=True)
        assert resistance == sorted(resistance)
