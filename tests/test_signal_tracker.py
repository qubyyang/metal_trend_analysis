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
