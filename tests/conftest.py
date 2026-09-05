"""pytest 共享 fixture"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 让测试可以 import src.*
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def indicator_config():
    """技术指标默认配置"""
    return {
        "ma": {"periods": [5, 10, 20, 60]},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "rsi": {"period": 14, "overbought": 70, "oversold": 30},
        "bollinger": {"period": 20, "std_dev": 2},
        "support_resistance": {"lookback": 100, "swing_points": 3, "proximity": 0.01},
    }


def _make_ohlc(closes, start="2024-01-01"):
    """由收盘价序列构造合法 OHLC 数据"""
    index = pd.date_range(start=start, periods=len(closes), freq="D")
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])

    highs = np.maximum(opens, closes) * 1.004
    lows = np.minimum(opens, closes) * 0.996

    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": 0},
        index=index,
    )


@pytest.fixture
def uptrend_df():
    """稳定上升趋势数据（120 根）"""
    closes = 2000 + np.arange(120) * 5.0
    return _make_ohlc(closes)


@pytest.fixture
def downtrend_df():
    """稳定下降趋势数据（120 根）"""
    closes = 2600 - np.arange(120) * 5.0
    return _make_ohlc(closes)


@pytest.fixture
def oscillating_df():
    """震荡行情数据（120 根）"""
    closes = 2000 + np.sin(np.arange(120) / 5.0) * 40
    return _make_ohlc(closes)


@pytest.fixture
def make_ohlc():
    """暴露构造函数供测试自定义序列"""
    return _make_ohlc
