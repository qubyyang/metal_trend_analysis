"""信号追踪与回测评估测试"""
import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.analyzers.signal_tracker import SignalTracker, normalize_direction


@pytest.fixture
def tracker(tmp_path):
    return SignalTracker({
        "signal_store": str(tmp_path / "signals.jsonl"),
        "horizon_days": 5,
        "threshold_pct": 0.5,
    })


class TestNormalizeDirection:
    @pytest.mark.parametrize("raw,expected", [
        ("bullish", "bullish"), ("看涨", "bullish"), ("多头", "bullish"),
        ("bearish", "bearish"), ("看跌", "bearish"), ("空头", "bearish"),
        ("neutral", "neutral"), ("震荡", "neutral"),
        (None, "neutral"), ("", "neutral"), ("无法识别的文本", "neutral"),
    ])
    def test_mapping(self, raw, expected):
        assert normalize_direction(raw) == expected

    def test_embedded_phrase(self):
        assert normalize_direction("短期趋势判断为看涨") == "bullish"


class TestRecord:
    def test_record_persists_signal(self, tracker):
        record = tracker.record(
            "XAUUSD",
            {"price": 2000.0},
            {"trend": "bullish", "macd_signal": "bullish", "rsi": 65.0},
        )

        assert record is not None
        assert record["technical_direction"] == "bullish"
        assert record["entry_price"] == 2000.0
        assert tracker.store_path.exists()

        lines = tracker.store_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["symbol"] == "XAUUSD"

    def test_record_without_price_returns_none(self, tracker):
        assert tracker.record("XAUUSD", {}, {"trend": "bullish"}) is None

    def test_llm_direction_extracted(self, tracker):
        record = tracker.record(
            "XAUUSD", {"price": 2000.0}, {"trend": "neutral"},
            llm_analysis={"analysis": {"trend": "看跌"}},
        )
        assert record["llm_direction"] == "bearish"

    def test_multiple_records_appended(self, tracker):
        for _ in range(3):
            tracker.record("XAUUSD", {"price": 2000.0}, {"trend": "bullish"})

        assert len(tracker.load_all()) == 3


class TestEvaluate:
    def _write(self, tracker, records):
        tracker.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracker.store_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _prices(self, start, values):
        index = pd.date_range(start=start, periods=len(values), freq="D")
        return pd.DataFrame({"close": values}, index=index)

    def test_correct_bullish_call_counts_as_win(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bullish", "horizon_days": 5,
        }])
        # 价格上涨 5%
        prices = self._prices(entry, np.linspace(2000, 2100, 10))

        stats = tracker.evaluate("XAUUSD", prices)
        assert stats["total_evaluated"] == 1
        assert stats["wins"] == 1
        assert stats["win_rate"] == 100.0

    def test_wrong_bullish_call_counts_as_loss(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bullish", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 1900, 10))

        stats = tracker.evaluate("XAUUSD", prices)
        assert stats["losses"] == 1
        assert stats["win_rate"] == 0.0

    def test_correct_bearish_call_counts_as_win(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bearish", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 1900, 10))

        stats = tracker.evaluate("XAUUSD", prices)
        assert stats["wins"] == 1
        # 看跌信号在下跌中获得正向收益
        assert stats["avg_return_pct"] > 0

    def test_small_move_counts_as_flat(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bullish", "horizon_days": 5,
        }])
        # 仅上涨 0.1%，低于 0.5% 阈值
        prices = self._prices(entry, np.linspace(2000, 2002, 10))

        stats = tracker.evaluate("XAUUSD", prices)
        assert stats["flats"] == 1
        assert stats["wins"] == 0 and stats["losses"] == 0

    def test_neutral_signals_excluded(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "neutral", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 2100, 10))

        assert tracker.evaluate("XAUUSD", prices)["total_evaluated"] == 0

    def test_immature_signal_not_evaluated(self, tracker):
        """持有期未结束的信号不应被计入"""
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bullish", "horizon_days": 30,
        }])
        prices = self._prices(entry, np.linspace(2000, 2100, 10))

        assert tracker.evaluate("XAUUSD", prices)["total_evaluated"] == 0

    def test_no_lookahead_bias(self, tracker):
        """只有信号时点之前的价格时，不得产生任何评估结果"""
        entry = datetime(2024, 6, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bullish", "horizon_days": 5,
        }])
        past_prices = self._prices(datetime(2024, 1, 1), np.linspace(1800, 2000, 30))

        assert tracker.evaluate("XAUUSD", past_prices)["total_evaluated"] == 0

    def test_other_symbols_excluded(self, tracker):
        entry = datetime(2024, 1, 1)
        self._write(tracker, [{
            "signal_id": "s1", "symbol": "XAGUSD",
            "created_at": entry.isoformat(), "entry_price": 25.0,
            "technical_direction": "bullish", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 2100, 10))

        assert tracker.evaluate("XAUUSD", prices)["total_evaluated"] == 0

    def test_empty_store_returns_zero_stats(self, tracker):
        prices = self._prices(datetime(2024, 1, 1), np.linspace(2000, 2100, 10))
        stats = tracker.evaluate("XAUUSD", prices)

        assert stats["total_evaluated"] == 0
        assert stats["profit_factor"] is None

    def test_win_rate_computation(self, tracker):
        """3 胜 1 负 → 胜率 75%"""
        entry = datetime(2024, 1, 1)
        records = []
        for i in range(3):
            records.append({
                "signal_id": f"w{i}", "symbol": "XAUUSD",
                "created_at": entry.isoformat(), "entry_price": 2000.0,
                "technical_direction": "bullish", "horizon_days": 5,
            })
        records.append({
            "signal_id": "l0", "symbol": "XAUUSD",
            "created_at": entry.isoformat(), "entry_price": 2000.0,
            "technical_direction": "bearish", "horizon_days": 5,
        })
        self._write(tracker, records)
        prices = self._prices(entry, np.linspace(2000, 2100, 10))

        stats = tracker.evaluate("XAUUSD", prices)
        assert stats["wins"] == 3 and stats["losses"] == 1
        assert stats["win_rate"] == 75.0


class TestFormatReport:
    def test_empty_stats_message(self, tracker):
        report = tracker.format_report(tracker._empty_stats("XAUUSD", "technical_direction"))
        assert "暂无已到期的信号" in report

    def test_small_sample_warning(self, tracker):
        stats = tracker._empty_stats("XAUUSD", "technical_direction")
        stats.update({"total_evaluated": 5, "wins": 3, "losses": 2, "win_rate": 60.0})

        report = tracker.format_report(stats)
        assert "60.00%" in report
        assert "样本量不足 30 条" in report


class TestExtendedStats:
    """分层胜率 / 最大回撤 / 显著性检验 / 基准对比"""

    def _write(self, tracker, records):
        tracker.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracker.store_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _prices(self, start, values):
        index = pd.date_range(start=start, periods=len(values), freq="D")
        return pd.DataFrame({"close": values}, index=index)

    # ---------------------------------------------------------- 最大回撤
    def test_max_drawdown_uses_chronological_order(self):
        """回撤必须按信号时间排序累计，乱序会算出错误结果"""
        base = pd.Timestamp("2024-01-01")
        evaluated = [
            {"entry_time": base + timedelta(days=2), "directional_return": -8.0,
             "outcome": "loss", "signal_score": None},
            {"entry_time": base, "directional_return": 5.0,
             "outcome": "win", "signal_score": None},
            {"entry_time": base + timedelta(days=4), "directional_return": 3.0,
             "outcome": "win", "signal_score": None},
        ]
        # 时序为 +5, -8, +3 -> 峰值 5，谷底 -3，回撤 -8
        assert SignalTracker._max_drawdown(evaluated) == pytest.approx(-8.0)

    def test_max_drawdown_zero_when_monotonic(self):
        base = pd.Timestamp("2024-01-01")
        evaluated = [
            {"entry_time": base + timedelta(days=i), "directional_return": 1.0,
             "outcome": "win", "signal_score": None}
            for i in range(5)
        ]
        assert SignalTracker._max_drawdown(evaluated) == 0.0

    def test_max_drawdown_empty(self):
        assert SignalTracker._max_drawdown([]) == 0.0

    # ---------------------------------------------------------- 显著性
    def test_significance_requires_30_samples(self):
        result = SignalTracker._significance(wins=15, decisive=20)
        assert result["sufficient_sample"] is False
        assert result["p_value"] is None

    def test_coin_flip_not_significant(self):
        """50 条里 28 胜看着像有 alpha，实际与随机无异"""
        result = SignalTracker._significance(wins=28, decisive=50)
        assert result["sufficient_sample"] is True
        assert result["p_value"] > 0.05
        assert "无显著差异" in result["verdict"]

    def test_strong_edge_is_significant(self):
        result = SignalTracker._significance(wins=70, decisive=100)
        assert result["p_value"] < 0.05
        assert "显著优于随机" in result["verdict"]

    def test_significantly_worse_detected(self):
        result = SignalTracker._significance(wins=30, decisive=100)
        assert result["p_value"] < 0.05
        assert "显著劣于随机" in result["verdict"]

    # ---------------------------------------------------------- 分层
    def test_score_buckets_split_by_strength(self):
        evaluated = (
            [{"signal_score": 60.0, "outcome": "win", "directional_return": 2.0}] * 6
            + [{"signal_score": 20.0, "outcome": "loss", "directional_return": -1.0}] * 4
        )
        buckets = SignalTracker._score_buckets(evaluated)
        by_band = {b["band"]: b for b in buckets}

        assert by_band["强信号 |score|>=40"]["win_rate"] == 100.0
        assert by_band["中等 15<=|score|<40"]["win_rate"] == 0.0

    def test_score_buckets_ignore_flats(self):
        evaluated = [
            {"signal_score": 50.0, "outcome": "win", "directional_return": 2.0},
            {"signal_score": 50.0, "outcome": "flat", "directional_return": 0.1},
        ]
        buckets = SignalTracker._score_buckets(evaluated)
        assert buckets[0]["count"] == 1

    def test_score_buckets_empty_without_scores(self):
        evaluated = [{"signal_score": None, "outcome": "win", "directional_return": 1.0}]
        assert SignalTracker._score_buckets(evaluated) == []

    def test_negative_scores_bucketed_by_magnitude(self):
        """看跌的强信号 score 是负数，应按绝对值归入强信号档"""
        evaluated = [
            {"signal_score": -55.0, "outcome": "win", "directional_return": 2.0}
        ]
        buckets = SignalTracker._score_buckets(evaluated)
        assert buckets[0]["band"] == "强信号 |score|>=40"

    # ---------------------------------------------------------- 基准
    def test_benchmark_computes_forward_returns(self, tracker):
        prices = self._prices(pd.Timestamp("2024-01-01"), np.linspace(100, 110, 60))
        benchmark = tracker.benchmark(prices)

        assert benchmark["available"] is True
        assert benchmark["horizon_days"] == 5
        assert benchmark["avg_return_pct"] > 0  # 单调上涨

    def test_benchmark_unavailable_on_short_series(self, tracker):
        prices = self._prices(pd.Timestamp("2024-01-01"), [100.0, 101.0])
        assert tracker.benchmark(prices)["available"] is False

    def test_benchmark_unavailable_on_empty(self, tracker):
        assert tracker.benchmark(pd.DataFrame())["available"] is False

    def test_format_benchmark_flags_underperformance(self, tracker):
        """策略跑输买入持有时必须明确警示，不能含糊带过"""
        stats = tracker._empty_stats("XAUUSD", "technical_direction")
        stats.update({"total_evaluated": 100, "win_rate": 53.0, "avg_return_pct": 0.11})
        benchmark = {"available": True, "horizon_days": 5, "samples": 500,
                     "up_rate": 47.0, "avg_return_pct": 0.32}

        text = tracker.format_benchmark("XAUUSD", stats, benchmark)
        assert "跑输" in text
        assert "不应据此实盘" in text

    def test_format_benchmark_recognizes_edge(self, tracker):
        stats = tracker._empty_stats("XAUUSD", "technical_direction")
        stats.update({"total_evaluated": 100, "win_rate": 60.0, "avg_return_pct": 0.90})
        benchmark = {"available": True, "horizon_days": 5, "samples": 500,
                     "up_rate": 47.0, "avg_return_pct": 0.32}

        assert "创造了" in tracker.format_benchmark("XAUUSD", stats, benchmark)

    # ---------------------------------------------------------- 衰减曲线
    def test_decay_curve_covers_all_horizons(self, tracker):
        entry = pd.Timestamp("2024-01-01T09:00:00")
        records = [{
            "signal_id": f"s{i}", "symbol": "XAUUSD",
            "created_at": (entry + timedelta(days=i)).isoformat(),
            "entry_price": 2000.0, "technical_direction": "bullish",
            "horizon_days": 5,
        } for i in range(5)]
        self._write(tracker, records)
        prices = self._prices(entry, np.linspace(2000, 2200, 60))

        curve = tracker.decay_curve("XAUUSD", prices, horizons=[1, 3, 5, 10])
        assert [c["horizon_days"] for c in curve] == [1, 3, 5, 10]
        assert all(c["evaluated"] > 0 for c in curve)

    def test_decay_curve_formatting(self, tracker):
        curve = [{"horizon_days": 5, "evaluated": 40, "win_rate": 55.0,
                  "avg_return_pct": 0.3, "profit_factor": 1.2}]
        text = tracker.format_decay_curve("XAUUSD", curve)
        assert "5 日" in text and "55.0%" in text

    def test_decay_curve_empty_when_no_samples(self, tracker):
        curve = [{"horizon_days": 5, "evaluated": 0, "win_rate": 0.0,
                  "avg_return_pct": 0.0, "profit_factor": None}]
        assert tracker.format_decay_curve("XAUUSD", curve) == ""

    # ---------------------------------------------------------- source 过滤
    def test_source_filter_separates_backfill_from_live(self, tracker):
        entry = pd.Timestamp("2024-01-01T09:00:00")
        records = [
            {"signal_id": "live1", "symbol": "XAUUSD", "created_at": entry.isoformat(),
             "entry_price": 2000.0, "technical_direction": "bullish", "horizon_days": 5},
            {"signal_id": "bf1", "symbol": "XAUUSD",
             "created_at": (entry + timedelta(days=1)).isoformat(),
             "entry_price": 2000.0, "technical_direction": "bullish",
             "horizon_days": 5, "source": "backfill"},
        ]
        self._write(tracker, records)
        prices = self._prices(entry, np.linspace(2000, 2200, 30))

        assert tracker.evaluate("XAUUSD", prices, source="live")["total_evaluated"] == 1
        assert tracker.evaluate("XAUUSD", prices, source="backfill")["total_evaluated"] == 1
        assert tracker.evaluate("XAUUSD", prices)["total_evaluated"] == 2

    def test_details_json_serializable(self, tracker):
        """details 含 Timestamp 会导致 JSON 序列化失败"""
        entry = pd.Timestamp("2024-01-01T09:00:00")
        self._write(tracker, [{
            "signal_id": "s0", "symbol": "XAUUSD", "created_at": entry.isoformat(),
            "entry_price": 2000.0, "technical_direction": "bullish", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 2200, 30))

        stats = tracker.evaluate("XAUUSD", prices)
        json.dumps(stats["details"], ensure_ascii=False)


class TestExtendedStats:
    """分层胜率 / 最大回撤 / 显著性检验 / 基准对比"""

    def _write(self, tracker, records):
        tracker.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tracker.store_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def _prices(self, start, values):
        index = pd.date_range(start=start, periods=len(values), freq="D")
        return pd.DataFrame({"close": values}, index=index)

    # ---------------------------------------------------------- 最大回撤
    def test_max_drawdown_uses_chronological_order(self):
        """回撤必须按信号时间排序累计，乱序会算出错误结果"""
        base = pd.Timestamp("2024-01-01")
        evaluated = [
            {"entry_time": base + timedelta(days=2), "directional_return": -8.0,
             "outcome": "loss", "signal_score": None},
            {"entry_time": base, "directional_return": 5.0,
             "outcome": "win", "signal_score": None},
            {"entry_time": base + timedelta(days=4), "directional_return": 3.0,
             "outcome": "win", "signal_score": None},
        ]
        # 时序为 +5, -8, +3 -> 峰值 5，谷底 -3，回撤 -8
        assert SignalTracker._max_drawdown(evaluated) == pytest.approx(-8.0)

    def test_max_drawdown_zero_when_monotonic(self):
        base = pd.Timestamp("2024-01-01")
        evaluated = [
            {"entry_time": base + timedelta(days=i), "directional_return": 1.0,
             "outcome": "win", "signal_score": None}
            for i in range(5)
        ]
        assert SignalTracker._max_drawdown(evaluated) == 0.0

    def test_max_drawdown_empty(self):
        assert SignalTracker._max_drawdown([]) == 0.0

    # ---------------------------------------------------------- 显著性
    def test_significance_requires_30_samples(self):
        result = SignalTracker._significance(wins=15, decisive=20)
        assert result["sufficient_sample"] is False
        assert result["p_value"] is None

    def test_coin_flip_not_significant(self):
        """50 条里 28 胜看着像有 alpha，实际与随机无异"""
        result = SignalTracker._significance(wins=28, decisive=50)
        assert result["sufficient_sample"] is True
        assert result["p_value"] > 0.05
        assert "无显著差异" in result["verdict"]

    def test_strong_edge_is_significant(self):
        result = SignalTracker._significance(wins=70, decisive=100)
        assert result["p_value"] < 0.05
        assert "显著优于随机" in result["verdict"]

    def test_significantly_worse_detected(self):
        result = SignalTracker._significance(wins=30, decisive=100)
        assert result["p_value"] < 0.05
        assert "显著劣于随机" in result["verdict"]

    # ---------------------------------------------------------- 分层
    def test_score_buckets_split_by_strength(self):
        evaluated = (
            [{"signal_score": 60.0, "outcome": "win", "directional_return": 2.0}] * 6
            + [{"signal_score": 20.0, "outcome": "loss", "directional_return": -1.0}] * 4
        )
        buckets = SignalTracker._score_buckets(evaluated)
        by_band = {b["band"]: b for b in buckets}

        assert by_band["强信号 |score|>=40"]["win_rate"] == 100.0
        assert by_band["中等 15<=|score|<40"]["win_rate"] == 0.0

    def test_score_buckets_ignore_flats(self):
        evaluated = [
            {"signal_score": 50.0, "outcome": "win", "directional_return": 2.0},
            {"signal_score": 50.0, "outcome": "flat", "directional_return": 0.1},
        ]
        buckets = SignalTracker._score_buckets(evaluated)
        assert buckets[0]["count"] == 1

    def test_score_buckets_empty_without_scores(self):
        evaluated = [{"signal_score": None, "outcome": "win", "directional_return": 1.0}]
        assert SignalTracker._score_buckets(evaluated) == []

    def test_negative_scores_bucketed_by_magnitude(self):
        """看跌的强信号 score 是负数，应按绝对值归入强信号档"""
        evaluated = [
            {"signal_score": -55.0, "outcome": "win", "directional_return": 2.0}
        ]
        buckets = SignalTracker._score_buckets(evaluated)
        assert buckets[0]["band"] == "强信号 |score|>=40"

    # ---------------------------------------------------------- 基准
    def test_benchmark_computes_forward_returns(self, tracker):
        prices = self._prices(pd.Timestamp("2024-01-01"), np.linspace(100, 110, 60))
        benchmark = tracker.benchmark(prices)

        assert benchmark["available"] is True
        assert benchmark["horizon_days"] == 5
        assert benchmark["avg_return_pct"] > 0  # 单调上涨

    def test_benchmark_unavailable_on_short_series(self, tracker):
        prices = self._prices(pd.Timestamp("2024-01-01"), [100.0, 101.0])
        assert tracker.benchmark(prices)["available"] is False

    def test_benchmark_unavailable_on_empty(self, tracker):
        assert tracker.benchmark(pd.DataFrame())["available"] is False

    def test_format_benchmark_flags_underperformance(self, tracker):
        """策略跑输买入持有时必须明确警示，不能含糊带过"""
        stats = tracker._empty_stats("XAUUSD", "technical_direction")
        stats.update({"total_evaluated": 100, "win_rate": 53.0, "avg_return_pct": 0.11})
        benchmark = {"available": True, "horizon_days": 5, "samples": 500,
                     "up_rate": 47.0, "avg_return_pct": 0.32}

        text = tracker.format_benchmark("XAUUSD", stats, benchmark)
        assert "跑输" in text
        assert "不应据此实盘" in text

    def test_format_benchmark_recognizes_edge(self, tracker):
        stats = tracker._empty_stats("XAUUSD", "technical_direction")
        stats.update({"total_evaluated": 100, "win_rate": 60.0, "avg_return_pct": 0.90})
        benchmark = {"available": True, "horizon_days": 5, "samples": 500,
                     "up_rate": 47.0, "avg_return_pct": 0.32}

        assert "创造了" in tracker.format_benchmark("XAUUSD", stats, benchmark)

    # ---------------------------------------------------------- 衰减曲线
    def test_decay_curve_covers_all_horizons(self, tracker):
        entry = pd.Timestamp("2024-01-01T09:00:00")
        records = [{
            "signal_id": f"s{i}", "symbol": "XAUUSD",
            "created_at": (entry + timedelta(days=i)).isoformat(),
            "entry_price": 2000.0, "technical_direction": "bullish",
            "horizon_days": 5,
        } for i in range(5)]
        self._write(tracker, records)
        prices = self._prices(entry, np.linspace(2000, 2200, 60))

        curve = tracker.decay_curve("XAUUSD", prices, horizons=[1, 3, 5, 10])
        assert [c["horizon_days"] for c in curve] == [1, 3, 5, 10]
        assert all(c["evaluated"] > 0 for c in curve)

    def test_decay_curve_formatting(self, tracker):
        curve = [{"horizon_days": 5, "evaluated": 40, "win_rate": 55.0,
                  "avg_return_pct": 0.3, "profit_factor": 1.2}]
        text = tracker.format_decay_curve("XAUUSD", curve)
        assert "5 日" in text and "55.0%" in text

    def test_decay_curve_empty_when_no_samples(self, tracker):
        curve = [{"horizon_days": 5, "evaluated": 0, "win_rate": 0.0,
                  "avg_return_pct": 0.0, "profit_factor": None}]
        assert tracker.format_decay_curve("XAUUSD", curve) == ""

    # ---------------------------------------------------------- source 过滤
    def test_source_filter_separates_backfill_from_live(self, tracker):
        entry = pd.Timestamp("2024-01-01T09:00:00")
        records = [
            {"signal_id": "live1", "symbol": "XAUUSD", "created_at": entry.isoformat(),
             "entry_price": 2000.0, "technical_direction": "bullish", "horizon_days": 5},
            {"signal_id": "bf1", "symbol": "XAUUSD",
             "created_at": (entry + timedelta(days=1)).isoformat(),
             "entry_price": 2000.0, "technical_direction": "bullish",
             "horizon_days": 5, "source": "backfill"},
        ]
        self._write(tracker, records)
        prices = self._prices(entry, np.linspace(2000, 2200, 30))

        assert tracker.evaluate("XAUUSD", prices, source="live")["total_evaluated"] == 1
        assert tracker.evaluate("XAUUSD", prices, source="backfill")["total_evaluated"] == 1
        assert tracker.evaluate("XAUUSD", prices)["total_evaluated"] == 2

    def test_details_json_serializable(self, tracker):
        """details 含 Timestamp 会导致 JSON 序列化失败"""
        entry = pd.Timestamp("2024-01-01T09:00:00")
        self._write(tracker, [{
            "signal_id": "s0", "symbol": "XAUUSD", "created_at": entry.isoformat(),
            "entry_price": 2000.0, "technical_direction": "bullish", "horizon_days": 5,
        }])
        prices = self._prices(entry, np.linspace(2000, 2200, 30))

        stats = tracker.evaluate("XAUUSD", prices)
        json.dumps(stats["details"], ensure_ascii=False)


class TestLLMConfidenceTracking:
    """LLM 层必须接受与技术层同等的证伪标准。"""

    def test_record_persists_llm_confidence(self, tracker):
        record = tracker.record(
            "XAUUSD",
            {"price": 2000.0},
            {"trend": "bullish"},
            llm_analysis={
                "analysis": {"trend": "看涨", "confidence": "高", "risk_level": "中"},
                "parse_mode": "json",
            },
        )
        assert record["llm_direction"] == "bullish"
        assert record["llm_confidence"] == "高"
        assert record["llm_risk_level"] == "中"
        assert record["llm_parse_mode"] == "json"

    def test_record_without_llm_leaves_fields_none(self, tracker):
        record = tracker.record("XAUUSD", {"price": 2000.0}, {"trend": "bullish"})
        assert record["llm_confidence"] is None
        assert record["llm_parse_mode"] is None

    @staticmethod
    def _seed(tracker, price_df, entries):
        """entries: [(confidence, direction, will_win)]"""
        base = price_df.index[0]
        for i, (conf, direction, win) in enumerate(entries):
            entry_price = 100.0
            tracker._append({
                "signal_id": f"S{i}",
                "symbol": "XAUUSD",
                "created_at": (base + timedelta(days=i)).isoformat(),
                "entry_price": entry_price,
                "technical_direction": direction,
                "llm_direction": direction,
                "llm_confidence": conf,
                "horizon_days": 5,
                "evaluated": False,
            })

    def test_confidence_buckets_detect_no_discrimination(self, tracker):
        """高置信档若不优于低置信档，必须明确判定为缺乏区分度。"""
        # 构造 40 天单调上涨行情，所有 bullish 信号都会赢
        idx = pd.date_range("2024-01-01", periods=60, freq="D")
        closes = np.linspace(100.0, 130.0, 60)
        price_df = pd.DataFrame({"close": closes}, index=idx)

        # 高置信 12 条全对，低置信 12 条也全对 -> 无区分度
        entries = [("高", "bullish", True)] * 12 + [("低", "bullish", True)] * 12
        self._seed(tracker, price_df, entries)

        buckets = tracker.confidence_buckets("XAUUSD", price_df)
        by = {b["confidence"]: b for b in buckets}
        assert "高" in by and "低" in by
        assert by["高"]["count"] == 12
        assert by["低"]["count"] == 12

        text = tracker.format_confidence_buckets("XAUUSD", price_df)
        assert "置信度缺乏区分度" in text

    def test_confidence_buckets_report_insufficient_sample(self, tracker):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 120.0, 40)}, index=idx)
        self._seed(tracker, price_df, [("高", "bullish", True)] * 3)

        text = tracker.format_confidence_buckets("XAUUSD", price_df)
        assert "样本不足" in text

    def test_confidence_buckets_empty_without_llm_records(self, tracker):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 120.0, 40)}, index=idx)
        tracker.record("XAUUSD", {"price": 100.0}, {"trend": "bullish"})
        assert tracker.confidence_buckets("XAUUSD", price_df) == []
        assert tracker.format_confidence_buckets("XAUUSD", price_df) == ""


class TestCollectEvaluatedNotTruncated:
    def test_full_sample_used_not_last_20(self, tracker):
        """details 只留最后 20 条用于展示；分层统计必须用全量，否则静默丢样本。"""
        idx = pd.date_range("2024-01-01", periods=90, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 160.0, 90)}, index=idx)
        base = idx[0]
        for i in range(40):
            tracker._append({
                "signal_id": f"T{i}",
                "symbol": "XAUUSD",
                "created_at": (base + timedelta(days=i)).isoformat(),
                "entry_price": 100.0,
                "technical_direction": "bullish",
                "horizon_days": 5,
                "evaluated": False,
            })

        full = tracker._collect_evaluated("XAUUSD", price_df, "technical_direction")
        stats = tracker.evaluate("XAUUSD", price_df, "technical_direction")
        assert len(full) == stats["total_evaluated"]
        assert len(full) > 20
        assert len(stats["details"]) == 20


class TestLLMConfidenceTracking:
    """LLM 层必须接受与技术层同等的证伪标准。"""

    def test_record_persists_llm_confidence(self, tracker):
        record = tracker.record(
            "XAUUSD",
            {"price": 2000.0},
            {"trend": "bullish"},
            llm_analysis={
                "analysis": {"trend": "看涨", "confidence": "高", "risk_level": "中"},
                "parse_mode": "json",
            },
        )
        assert record["llm_direction"] == "bullish"
        assert record["llm_confidence"] == "高"
        assert record["llm_risk_level"] == "中"
        assert record["llm_parse_mode"] == "json"

    def test_record_without_llm_leaves_fields_none(self, tracker):
        record = tracker.record("XAUUSD", {"price": 2000.0}, {"trend": "bullish"})
        assert record["llm_confidence"] is None
        assert record["llm_parse_mode"] is None

    @staticmethod
    def _seed(tracker, price_df, entries):
        """entries: [(confidence, direction, will_win)]"""
        base = price_df.index[0]
        for i, (conf, direction, win) in enumerate(entries):
            entry_price = 100.0
            tracker._append({
                "signal_id": f"S{i}",
                "symbol": "XAUUSD",
                "created_at": (base + timedelta(days=i)).isoformat(),
                "entry_price": entry_price,
                "technical_direction": direction,
                "llm_direction": direction,
                "llm_confidence": conf,
                "horizon_days": 5,
                "evaluated": False,
            })

    def test_confidence_buckets_detect_no_discrimination(self, tracker):
        """高置信档若不优于低置信档，必须明确判定为缺乏区分度。"""
        # 构造 40 天单调上涨行情，所有 bullish 信号都会赢
        idx = pd.date_range("2024-01-01", periods=60, freq="D")
        closes = np.linspace(100.0, 130.0, 60)
        price_df = pd.DataFrame({"close": closes}, index=idx)

        # 高置信 12 条全对，低置信 12 条也全对 -> 无区分度
        entries = [("高", "bullish", True)] * 12 + [("低", "bullish", True)] * 12
        self._seed(tracker, price_df, entries)

        buckets = tracker.confidence_buckets("XAUUSD", price_df)
        by = {b["confidence"]: b for b in buckets}
        assert "高" in by and "低" in by
        assert by["高"]["count"] == 12
        assert by["低"]["count"] == 12

        text = tracker.format_confidence_buckets("XAUUSD", price_df)
        assert "置信度缺乏区分度" in text

    def test_confidence_buckets_report_insufficient_sample(self, tracker):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 120.0, 40)}, index=idx)
        self._seed(tracker, price_df, [("高", "bullish", True)] * 3)

        text = tracker.format_confidence_buckets("XAUUSD", price_df)
        assert "样本不足" in text

    def test_confidence_buckets_empty_without_llm_records(self, tracker):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 120.0, 40)}, index=idx)
        tracker.record("XAUUSD", {"price": 100.0}, {"trend": "bullish"})
        assert tracker.confidence_buckets("XAUUSD", price_df) == []
        assert tracker.format_confidence_buckets("XAUUSD", price_df) == ""


class TestCollectEvaluatedNotTruncated:
    def test_full_sample_used_not_last_20(self, tracker):
        """details 只留最后 20 条用于展示；分层统计必须用全量，否则静默丢样本。"""
        idx = pd.date_range("2024-01-01", periods=90, freq="D")
        price_df = pd.DataFrame({"close": np.linspace(100.0, 160.0, 90)}, index=idx)
        base = idx[0]
        for i in range(40):
            tracker._append({
                "signal_id": f"T{i}",
                "symbol": "XAUUSD",
                "created_at": (base + timedelta(days=i)).isoformat(),
                "entry_price": 100.0,
                "technical_direction": "bullish",
                "horizon_days": 5,
                "evaluated": False,
            })

        full = tracker._collect_evaluated("XAUUSD", price_df, "technical_direction")
        stats = tracker.evaluate("XAUUSD", price_df, "technical_direction")
        assert len(full) == stats["total_evaluated"]
        assert len(full) > 20
        assert len(stats["details"]) == 20
