"""图表生成模块测试"""
import pytest

from src.analyzers.technical import TechnicalAnalyzer
from src.reporting.chart import MATPLOTLIB_AVAILABLE, ChartGenerator


@pytest.fixture
def generator(tmp_path):
    return ChartGenerator({"chart_dir": str(tmp_path / "charts"), "chart_bars": 60})


@pytest.fixture
def indicator_df(indicator_config, uptrend_df):
    return TechnicalAnalyzer(indicator_config).calculate_all_indicators(uptrend_df)


class TestGracefulDegradation:
    """matplotlib 缺失时必须降级而非崩溃"""

    def test_available_flag_matches_import(self, generator):
        assert generator.available == MATPLOTLIB_AVAILABLE

    def test_empty_dataframe_returns_none(self, generator):
        import pandas as pd
        assert generator.generate(pd.DataFrame(), "XAUUSD") is None

    def test_none_dataframe_returns_none(self, generator):
        assert generator.generate(None, "XAUUSD") is None

    def test_single_row_returns_none(self, generator, indicator_df):
        assert generator.generate(indicator_df.head(1), "XAUUSD") is None


@pytest.mark.skipif(not MATPLOTLIB_AVAILABLE, reason="matplotlib 未安装")
class TestChartRendering:
    def test_generates_png_file(self, generator, indicator_df):
        path = generator.generate(indicator_df, "XAUUSD", "国际现货黄金", "1d")

        assert path is not None
        assert path.exists()
        assert path.suffix == ".png"
        assert path.stat().st_size > 1000, "图片文件过小，可能渲染失败"

    def test_renders_with_support_resistance(self, generator, indicator_df):
        path = generator.generate(
            indicator_df, "XAUUSD", "国际现货黄金", "1d",
            support_levels=[2100.0, 2050.0],
            resistance_levels=[2500.0, 2550.0],
        )
        assert path is not None and path.exists()

    def test_handles_missing_indicator_columns(self, generator, uptrend_df):
        """仅有 OHLC、无指标列时也应产出图表"""
        path = generator.generate(uptrend_df, "XAUUSD")
        assert path is not None and path.exists()

    def test_respects_bars_limit(self, generator, indicator_df):
        generator.bars = 20
        path = generator.generate(indicator_df, "XAUUSD")
        assert path is not None and path.exists()

    def test_no_figure_leak(self, generator, indicator_df):
        """连续生成不得泄漏 matplotlib 画布"""
        import matplotlib.pyplot as plt

        for _ in range(3):
            generator.generate(indicator_df, "XAUUSD")

        assert len(plt.get_fignums()) == 0, "存在未关闭的画布"
