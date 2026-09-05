"""因子化信号引擎测试

覆盖重点：
- 各因子的方向语义（尤其 RSI 的反转语义与趋势类因子相反）
- 无效因子的**权重重归一化**（而非按中性值稀释）
- 成交量恒为 0 时必须判定为 invalid
- 波动率闸门只衰减强度、不改变方向
"""
import numpy as np
import pandas as pd
import pytest

from src.analyzers.signal_engine import DEFAULT_WEIGHTS, FactorScore, SignalEngine


def make_row(**kwargs) -> pd.Series:
    base = {
        "close": 100.0,
        "MA5": 100.0,
        "MA10": 100.0,
        "MA20": 100.0,
        "MACD_DIF": 0.0,
        "MACD_DEA": 0.0,
        "MACD_HIST": 0.0,
        "RSI": 50.0,
        "BB_UPPER": 110.0,
        "BB_MIDDLE": 100.0,
        "BB_LOWER": 90.0,
        "ATR": 1.0,
    }
    base.update(kwargs)
    return pd.Series(base)


def make_df(n: int = 120, trend: float = 0.0, volume: float = 0.0) -> pd.DataFrame:
    """构造带日期索引的合成 K 线，trend 为每根的线性涨跌幅度"""
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 100.0 + np.arange(n) * trend
    df = pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.full(n, volume, dtype=float),
        },
        index=idx,
    )
    return df


# ---------------------------------------------------------------- FactorScore
class TestFactorScore:
    def test_score_clipped_to_unit_range(self):
        assert FactorScore("x", 5.0).score == 1.0
        assert FactorScore("x", -5.0).score == -1.0

    def test_invalid_factor_score_forced_zero(self):
        f = FactorScore("x", 0.9, valid=False, weight=0.3)
        assert f.score == 0.0
        assert f.valid is False


# ---------------------------------------------------------------- 均线因子
class TestMaAlignment:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_bullish_alignment_positive(self):
        row = make_row(MA5=110, MA10=105, MA20=100, close=112)
        f = self.engine._factor_ma_alignment(row)
        assert f.valid and f.score == pytest.approx(1.0)
        assert "完全多头排列" in f.detail

    def test_bearish_alignment_negative(self):
        row = make_row(MA5=90, MA10=95, MA20=100, close=88)
        f = self.engine._factor_ma_alignment(row)
        assert f.score == pytest.approx(-1.0)

    def test_tangled_ma_between_extremes(self):
        row = make_row(MA5=105, MA10=98, MA20=100, close=105)
        f = self.engine._factor_ma_alignment(row)
        assert -1.0 < f.score < 1.0

    def test_insufficient_ma_marked_invalid(self):
        row = pd.Series({"close": 100.0, "MA5": 100.0})
        f = self.engine._factor_ma_alignment(row)
        assert f.valid is False


# ---------------------------------------------------------------- MACD
class TestMacd:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_golden_cross_above_axis_max(self):
        f = self.engine._factor_macd(make_row(MACD_DIF=0.8, MACD_DEA=0.3))
        assert f.score == pytest.approx(1.0)

    def test_death_cross_below_axis_min(self):
        f = self.engine._factor_macd(make_row(MACD_DIF=-0.8, MACD_DEA=-0.3))
        assert f.score == pytest.approx(-1.0)

    def test_cross_straddling_axis_is_partial(self):
        f = self.engine._factor_macd(make_row(MACD_DIF=0.2, MACD_DEA=-0.1))
        assert f.score == pytest.approx(0.6)

    def test_missing_macd_invalid(self):
        row = make_row()
        row = row.drop(labels=["MACD_DIF"])
        assert self.engine._factor_macd(row).valid is False


# ---------------------------------------------------------------- RSI
class TestRsi:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_overbought_is_bearish_not_bullish(self):
        """RSI 是摆动指标：超买给看跌提示，方向与趋势类因子相反"""
        f = self.engine._factor_rsi(make_row(RSI=85))
        assert f.score < 0

    def test_oversold_is_bullish(self):
        assert self.engine._factor_rsi(make_row(RSI=15)).score > 0

    def test_deeper_overbought_stronger_signal(self):
        shallow = self.engine._factor_rsi(make_row(RSI=72)).score
        deep = self.engine._factor_rsi(make_row(RSI=95)).score
        assert deep < shallow < 0

    def test_neutral_zone_bounded_by_half(self):
        for rsi in (40, 50, 60):
            assert abs(self.engine._factor_rsi(make_row(RSI=rsi)).score) <= 0.5

    def test_rsi_50_is_zero(self):
        assert self.engine._factor_rsi(make_row(RSI=50)).score == pytest.approx(0.0)


# ---------------------------------------------------------------- 布林带
class TestBollinger:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_near_upper_band_is_bullish_trend_following(self):
        f = self.engine._factor_bollinger(make_row(close=109))
        assert f.score > 0.7

    def test_below_lower_band_clipped_to_minus_one(self):
        f = self.engine._factor_bollinger(make_row(close=80))
        assert f.score == pytest.approx(-1.0)
        assert "跌破下轨" in f.detail

    def test_zero_width_channel_invalid(self):
        f = self.engine._factor_bollinger(make_row(BB_UPPER=100, BB_LOWER=100))
        assert f.valid is False


# ---------------------------------------------------------------- 成交量
class TestVolume:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_all_zero_volume_marked_invalid(self):
        """新浪现货金银 volume 恒为 0，必须剔除而不是当作缩量给负分"""
        df = make_df(volume=0.0)
        f = self.engine._factor_volume(df, df.iloc[-1])
        assert f.valid is False
        assert "剔除" in f.detail

    def test_missing_volume_column_invalid(self):
        df = make_df().drop(columns=["volume"])
        f = self.engine._factor_volume(df, df.iloc[-1])
        assert f.valid is False

    def test_expansion_with_rising_price_positive(self):
        df = make_df(trend=0.5, volume=1000.0)
        df.iloc[-1, df.columns.get_loc("volume")] = 2500.0
        f = self.engine._factor_volume(df, df.iloc[-1])
        assert f.valid and f.score > 0

    def test_expansion_with_falling_price_negative(self):
        df = make_df(trend=-0.5, volume=1000.0)
        df.iloc[-1, df.columns.get_loc("volume")] = 2500.0
        f = self.engine._factor_volume(df, df.iloc[-1])
        assert f.valid and f.score < 0


# ---------------------------------------------------------------- 多周期
class TestMultiPeriod:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_uptrend_resonance_positive(self):
        df = make_df(n=200, trend=0.5)
        f = self.engine._factor_multi_period(df)
        assert f.valid and f.score == pytest.approx(1.0)
        assert "共振" in f.detail

    def test_downtrend_resonance_negative(self):
        df = make_df(n=200, trend=-0.5)
        f = self.engine._factor_multi_period(df)
        assert f.score == pytest.approx(-1.0)

    def test_short_sample_invalid(self):
        f = self.engine._factor_multi_period(make_df(n=10))
        assert f.valid is False

    def test_non_datetime_index_invalid(self):
        df = make_df(n=200, trend=0.5).reset_index(drop=True)
        f = self.engine._factor_multi_period(df)
        assert f.valid is False


# ---------------------------------------------------------------- 聚合
class TestAggregate:
    def test_invalid_factor_weight_redistributed_not_diluted(self):
        """核心行为：无效因子让出权重，不得把评分往中性拉"""
        factors = [
            FactorScore("a", 1.0, True, 0.5),
            FactorScore("b", 0.0, False, 0.5),
        ]
        agg = SignalEngine._aggregate(factors)
        # 若按稀释处理会得到 0.5；正确结果应为 1.0
        assert agg["raw_score"] == pytest.approx(1.0)
        assert agg["valid_count"] == 1
        assert agg["total_weight"] == pytest.approx(0.5)

    def test_all_invalid_returns_zero(self):
        agg = SignalEngine._aggregate([FactorScore("a", 0.0, False, 0.5)])
        assert agg["raw_score"] == 0.0
        assert agg["valid_count"] == 0

    def test_weighted_average(self):
        factors = [
            FactorScore("a", 1.0, True, 0.75),
            FactorScore("b", -1.0, True, 0.25),
        ]
        assert SignalEngine._aggregate(factors)["raw_score"] == pytest.approx(0.5)


# ---------------------------------------------------------------- 波动率闸门
class TestVolatilityGate:
    def setup_method(self):
        self.engine = SignalEngine()

    def test_normal_volatility_no_damping(self):
        gate = self.engine._volatility_gate(make_row(ATR=1.0, close=100.0))
        assert gate["damping"] == 1.0

    def test_high_volatility_damped(self):
        gate = self.engine._volatility_gate(make_row(ATR=6.0, close=100.0))
        assert gate["damping"] < 1.0

    def test_damping_floor_respected(self):
        gate = self.engine._volatility_gate(make_row(ATR=50.0, close=100.0))
        assert gate["damping"] == pytest.approx(self.engine.max_volatility_damping)

    def test_missing_atr_no_damping(self):
        row = make_row().drop(labels=["ATR"])
        assert self.engine._volatility_gate(row)["damping"] == 1.0


# ---------------------------------------------------------------- 端到端
class TestEvaluate:
    def setup_method(self):
        self.engine = SignalEngine()

    def _decorate(self, df: pd.DataFrame, **overrides) -> pd.DataFrame:
        close = df["close"]
        df = df.copy()
        df["MA5"] = close.rolling(5).mean()
        df["MA10"] = close.rolling(10).mean()
        df["MA20"] = close.rolling(20).mean()
        std = close.rolling(20).std().fillna(1.0)
        df["BB_MIDDLE"] = df["MA20"]
        df["BB_UPPER"] = df["MA20"] + 2 * std
        df["BB_LOWER"] = df["MA20"] - 2 * std
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        df["MACD_DIF"] = ema12 - ema26
        df["MACD_DEA"] = df["MACD_DIF"].ewm(span=9).mean()
        df["MACD_HIST"] = 2 * (df["MACD_DIF"] - df["MACD_DEA"])
        df["RSI"] = 55.0
        df["ATR"] = 1.0
        for k, v in overrides.items():
            df[k] = v
        return df

    def test_empty_df_returns_unavailable(self):
        result = self.engine.evaluate(pd.DataFrame())
        assert result["available"] is False
        assert result["direction"] == "neutral"

    def test_uptrend_produces_bullish_score(self):
        df = self._decorate(make_df(n=200, trend=0.5))
        result = self.engine.evaluate(df)
        assert result["available"] is True
        assert result["score"] > 0
        assert result["direction"] in ("bullish", "strong_bullish")

    def test_downtrend_produces_bearish_score(self):
        df = self._decorate(make_df(n=200, trend=-0.5))
        result = self.engine.evaluate(df)
        assert result["score"] < 0
        assert result["direction"] in ("bearish", "strong_bearish")

    def test_zero_volume_excluded_from_factors(self):
        df = self._decorate(make_df(n=200, trend=0.5, volume=0.0))
        result = self.engine.evaluate(df)
        assert "volume" in result["excluded_factors"]
        # 有效权重应等于总权重减去 volume 权重
        expected = sum(DEFAULT_WEIGHTS.values()) - DEFAULT_WEIGHTS["volume"]
        assert result["effective_weight"] == pytest.approx(expected, abs=1e-6)

    def test_score_bounded(self):
        df = self._decorate(make_df(n=200, trend=2.0))
        result = self.engine.evaluate(df)
        assert -100.0 <= result["score"] <= 100.0

    def test_volatility_damping_reduces_magnitude_not_direction(self):
        df = self._decorate(make_df(n=200, trend=0.5))
        calm = self.engine.evaluate(df)
        volatile = self.engine.evaluate(self._decorate(make_df(n=200, trend=0.5), ATR=15.0))
        assert volatile["score"] > 0  # 方向不变
        assert abs(volatile["score"]) < abs(calm["score"])
        assert volatile["confidence"] < calm["confidence"]

    def test_disabled_factor_excluded_entirely(self):
        engine = SignalEngine({"weights": {"rsi": 0}})
        df = self._decorate(make_df(n=200, trend=0.5))
        names = [f["name"] for f in engine.evaluate(df)["factors"]]
        assert "rsi" not in names

    def test_negative_weight_rejected(self):
        engine = SignalEngine({"weights": {"macd": -0.5}})
        assert "macd" not in engine.weights


class TestLabel:
    def test_thresholds(self):
        e = SignalEngine()
        assert e._label(60) == "strong_bullish"
        assert e._label(25) == "bullish"
        assert e._label(0) == "neutral"
        assert e._label(-25) == "bearish"
        assert e._label(-60) == "strong_bearish"
