"""历史信号回填测试

重点验证前视偏差防护——回填最容易犯的错就是让历史信号看到未来数据。
"""
import json

import numpy as np
import pandas as pd
import pytest

from src.analyzers.signal_backfill import SignalBackfiller
from src.analyzers.signal_tracker import SignalTracker
from src.analyzers.technical import TechnicalAnalyzer


@pytest.fixture
def analyzer():
    return TechnicalAnalyzer({"ma": {"periods": [5, 10, 20, 60]}})


@pytest.fixture
def tracker(tmp_path):
    return SignalTracker({
        "signal_store": str(tmp_path / "signals.jsonl"),
        "horizon_days": 5,
    })


def make_df(n=400, trend=0.3, noise=0.0, seed=42):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    close = 100.0 + np.arange(n) * trend
    if noise:
        close = close + rng.normal(0, noise, n)
    close = np.maximum(close, 1.0)
    return pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.full(n, 1000.0),
    }, index=idx)


class TestNoLookahead:
    def test_indicators_are_causal(self, analyzer):
        """回填依赖「截断重算等于全量切片」这一前提，必须显式验证

        若未来引入非因果指标（centered rolling、全样本 zscore），
        这个测试会失败，提醒必须改回逐日重算。
        """
        df = make_df(n=300, noise=2.0)
        full = analyzer.calculate_all_indicators(df)
        truncated = analyzer.calculate_all_indicators(df.iloc[:250].copy())

        for col in ["MA5", "MA20", "MA60", "MACD_DIF", "MACD_DEA",
                    "RSI", "BB_UPPER", "BB_LOWER", "ATR"]:
            a = full[col].iloc[249]
            b = truncated[col].iloc[249]
            assert a == pytest.approx(b, abs=1e-9), f"{col} 非因果：全量与截断结果不一致"

    def test_entry_price_matches_bar_close(self, analyzer, tracker):
        """入场价必须是信号当日收盘，不能取后续任何一根"""
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        records = bf.backfill("TEST", df, dry_run=True)

        assert records
        closes = df["close"]
        for record in records:
            bar_time = pd.Timestamp(record["created_at"])
            assert record["entry_price"] == pytest.approx(float(closes.loc[bar_time]))

    def test_created_at_uses_bar_time_not_now(self, analyzer, tracker):
        """created_at 必须是 K 线时间，否则评估时会匹配错未来价格"""
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        records = bf.backfill("TEST", df, dry_run=True)

        last_bar = df.index[-1]
        for record in records:
            assert pd.Timestamp(record["created_at"]) <= last_bar

    def test_signal_only_depends_on_past_bars(self, analyzer, tracker):
        """篡改未来数据不应改变历史信号

        这是前视偏差最直接的检验：把第 250 根之后的价格全部改掉，
        第 200 根的信号评分必须完全不变。
        """
        df = make_df(n=300, noise=2.0)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 150, "step_bars": 5})

        original = bf.backfill("TEST", df, dry_run=True)

        tampered = df.copy()
        tampered.iloc[250:, tampered.columns.get_loc("close")] *= 3.0
        tampered.iloc[250:, tampered.columns.get_loc("high")] *= 3.0
        tampered.iloc[250:, tampered.columns.get_loc("low")] *= 3.0
        modified = bf.backfill("TEST", tampered, dry_run=True)

        orig_map = {r["created_at"]: r["signal_score"] for r in original}
        mod_map = {r["created_at"]: r["signal_score"] for r in modified}

        cutoff = df.index[250]
        compared = 0
        for created_at, score in orig_map.items():
            if pd.Timestamp(created_at) >= cutoff:
                continue
            assert mod_map[created_at] == pytest.approx(score), \
                f"{created_at} 的信号受到了未来数据影响"
            compared += 1

        assert compared > 10, "有效对比样本过少，测试无意义"


class TestSampling:
    def test_step_defaults_to_horizon(self, analyzer, tracker):
        """默认采样间隔应与持有期对齐，避免重叠样本高估显著性"""
        bf = SignalBackfiller(analyzer, tracker)
        assert bf.step == tracker.horizon_days

    def test_step_is_respected(self, analyzer, tracker):
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 100, "step_bars": 10})
        records = bf.backfill("TEST", df, dry_run=True)

        times = [pd.Timestamp(r["created_at"]) for r in records]
        assert len(times) == len(set(times))
        # 相邻样本至少间隔 10 个交易日
        for a, b in zip(times, times[1:]):
            assert (b - a).days >= 10

    def test_warmup_bars_skipped(self, analyzer, tracker):
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 200, "step_bars": 1})
        records = bf.backfill("TEST", df, dry_run=True)

        first = pd.Timestamp(records[0]["created_at"])
        assert first >= df.index[200]

    def test_short_history_returns_empty(self, analyzer, tracker):
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        assert bf.backfill("TEST", make_df(n=50), dry_run=True) == []

    def test_empty_df_returns_empty(self, analyzer, tracker):
        bf = SignalBackfiller(analyzer, tracker)
        assert bf.backfill("TEST", pd.DataFrame(), dry_run=True) == []


class TestPersistence:
    def test_dry_run_writes_nothing(self, analyzer, tracker):
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        bf.backfill("TEST", make_df(n=300), dry_run=True)
        assert tracker.load_all() == []

    def test_records_written_and_loadable(self, analyzer, tracker):
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        records = bf.backfill("TEST", make_df(n=300))

        stored = tracker.load_all()
        assert len(stored) == len(records)
        assert all(r["source"] == "backfill" for r in stored)

    def test_idempotent_on_rerun(self, analyzer, tracker):
        """重复回填同一区间不应产生重复样本"""
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})

        first = bf.backfill("TEST", df)
        second = bf.backfill("TEST", df)

        assert first
        assert second == []
        assert len(tracker.load_all()) == len(first)

    def test_other_symbols_not_blocked(self, analyzer, tracker):
        df = make_df(n=300)
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        bf.backfill("AAA", df)
        second = bf.backfill("BBB", df)
        assert second, "不同品种的同日信号不应互相去重"

    def test_direction_coarsened_for_legacy_field(self, analyzer, tracker):
        """technical_direction 只能是 bullish/bearish/neutral 三值"""
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        records = bf.backfill("TEST", make_df(n=300), dry_run=True)
        assert {r["technical_direction"] for r in records} <= {
            "bullish", "bearish", "neutral"
        }

    def test_record_is_json_serializable(self, analyzer, tracker):
        bf = SignalBackfiller(analyzer, tracker, {"warmup_bars": 120})
        records = bf.backfill("TEST", make_df(n=300), dry_run=True)
        for record in records[:5]:
            json.loads(json.dumps(record, ensure_ascii=False))
