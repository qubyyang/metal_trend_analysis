"""
K 线图表生成模块

基于 matplotlib 生成包含 K 线、均线、布林带、MACD、RSI 的组合图，
供报告嵌入与通知渠道推送使用。matplotlib 为可选依赖，未安装时优雅降级。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from loguru import logger

try:  # matplotlib 为可选依赖
    import matplotlib
    matplotlib.use("Agg")  # 无 GUI 环境后端
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    MATPLOTLIB_AVAILABLE = False


# A 股/国内习惯：涨红跌绿
COLOR_UP = "#D32F2F"
COLOR_DOWN = "#2E7D32"
COLOR_MA = ["#1976D2", "#F57C00", "#7B1FA2", "#00838F"]
COLOR_GRID = "#E0E0E0"
COLOR_BB = "#9E9E9E"

# 跨平台中文字体候选（macOS / Windows / Linux）
_CJK_FONT_CANDIDATES = [
    "PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti",
    "Microsoft YaHei", "SimHei",
    "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Zen Hei",
    "Arial Unicode MS",
]

_font_configured = False


def _configure_cjk_font() -> Optional[str]:
    """
    配置 matplotlib 中文字体，避免中文标签渲染为豆腐块。

    Returns:
        实际选用的字体名；未找到可用中文字体时返回 None
    """
    global _font_configured

    if not MATPLOTLIB_AVAILABLE or _font_configured:
        return None

    _font_configured = True

    try:
        from matplotlib import font_manager

        installed = {f.name for f in font_manager.fontManager.ttflist}
        chosen = next((n for n in _CJK_FONT_CANDIDATES if n in installed), None)

        if chosen:
            matplotlib.rcParams["font.sans-serif"] = [chosen] + _CJK_FONT_CANDIDATES
            matplotlib.rcParams["font.family"] = "sans-serif"
        else:
            logger.warning(
                "未检测到可用中文字体，图表中文标签可能显示异常。"
                "建议安装 Noto Sans CJK SC 或系统中文字体。"
            )

        # 中文字体常缺 Unicode 负号，统一回退为 ASCII 连字符
        matplotlib.rcParams["axes.unicode_minus"] = False
        return chosen

    except Exception as e:  # pragma: no cover - 字体探测失败不应阻断出图
        logger.warning(f"中文字体配置失败，使用默认字体: {e}")
        return None


class ChartGenerator:
    """技术分析图表生成器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        self.output_dir = Path(self.config.get("chart_dir", "output/charts"))
        self.dpi = self.config.get("chart_dpi", 130)
        self.bars = self.config.get("chart_bars", 120)
        self.figsize = self.config.get("chart_figsize", (12, 9))

        _configure_cjk_font()

    @property
    def available(self) -> bool:
        """matplotlib 是否可用"""
        return MATPLOTLIB_AVAILABLE

    # ------------------------------------------------------------------
    def generate(
        self,
        df: pd.DataFrame,
        symbol: str,
        symbol_name: str = "",
        timeframe: str = "1d",
        support_levels: Optional[List[float]] = None,
        resistance_levels: Optional[List[float]] = None,
    ) -> Optional[Path]:
        """生成技术分析组合图

        Args:
            df: 含指标列的 DataFrame（calculate_all_indicators 输出）
            symbol: 品种代码
            symbol_name: 品种中文名
            timeframe: 周期标识
            support_levels: 支撑位列表
            resistance_levels: 阻力位列表

        Returns:
            图片路径；matplotlib 不可用或生成失败时返回 None
        """
        if not MATPLOTLIB_AVAILABLE:
            self.logger.warning("matplotlib 未安装，跳过图表生成（pip install matplotlib）")
            return None

        if df is None or df.empty:
            self.logger.warning(f"{symbol} 无数据，跳过图表生成")
            return None

        try:
            plot_df = df.tail(self.bars).copy()
            if len(plot_df) < 2:
                self.logger.warning(f"{symbol} 数据点不足，跳过图表生成")
                return None

            fig, (ax_price, ax_macd, ax_rsi) = plt.subplots(
                3, 1,
                figsize=self.figsize,
                dpi=self.dpi,
                sharex=True,
                gridspec_kw={"height_ratios": [3, 1, 1], "hspace": 0.08},
            )

            self._plot_price(ax_price, plot_df, support_levels, resistance_levels)
            self._plot_macd(ax_macd, plot_df)
            self._plot_rsi(ax_rsi, plot_df)

            title = f"{symbol_name or symbol} ({symbol}) · {timeframe}"
            ax_price.set_title(title, fontsize=13, fontweight="bold", pad=12)

            ax_rsi.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            fig.autofmt_xdate(rotation=30)

            return self._save(fig, symbol, timeframe)

        except Exception as e:
            self.logger.error(f"{symbol} 图表生成失败: {e}")
            plt.close("all")
            return None

    # ------------------------------------------------------------------
    def _plot_price(
        self,
        ax,
        df: pd.DataFrame,
        support_levels: Optional[List[float]],
        resistance_levels: Optional[List[float]],
    ) -> None:
        """绘制 K 线 + 均线 + 布林带 + 支撑阻力"""
        # 依据数据密度自适应蜡烛宽度
        width = max((df.index[-1] - df.index[0]).days / len(df) * 0.6, 0.3)

        for timestamp, row in df.iterrows():
            is_up = row["close"] >= row["open"]
            color = COLOR_UP if is_up else COLOR_DOWN

            # 影线
            ax.plot(
                [timestamp, timestamp], [row["low"], row["high"]],
                color=color, linewidth=0.8, zorder=2,
            )
            # 实体
            body_low = min(row["open"], row["close"])
            body_height = abs(row["close"] - row["open"]) or (row["close"] * 0.0005)
            ax.bar(
                timestamp, body_height, bottom=body_low,
                width=width, color=color, edgecolor=color, zorder=3,
            )

        # 均线
        ma_columns = sorted(
            [c for c in df.columns if c.startswith("MA") and c[2:].isdigit()],
            key=lambda c: int(c[2:]),
        )
        for i, col in enumerate(ma_columns):
            ax.plot(
                df.index, df[col],
                label=col, linewidth=1.2,
                color=COLOR_MA[i % len(COLOR_MA)], zorder=4,
            )

        # 布林带
        if {"BB_UPPER", "BB_LOWER"}.issubset(df.columns):
            ax.plot(df.index, df["BB_UPPER"], color=COLOR_BB,
                    linewidth=0.8, linestyle="--", alpha=0.7, zorder=1)
            ax.plot(df.index, df["BB_LOWER"], color=COLOR_BB,
                    linewidth=0.8, linestyle="--", alpha=0.7, zorder=1)
            ax.fill_between(df.index, df["BB_LOWER"], df["BB_UPPER"],
                            color=COLOR_BB, alpha=0.08, zorder=0)

        # 支撑/阻力位（各取最靠近现价的两档）
        for level in (resistance_levels or [])[:2]:
            ax.axhline(level, color=COLOR_DOWN, linewidth=0.8,
                       linestyle=":", alpha=0.8, zorder=1)
            ax.annotate(f"阻力 {level:.2f}", xy=(df.index[0], level),
                        fontsize=8, color=COLOR_DOWN, va="bottom")

        for level in (support_levels or [])[:2]:
            ax.axhline(level, color=COLOR_UP, linewidth=0.8,
                       linestyle=":", alpha=0.8, zorder=1)
            ax.annotate(f"支撑 {level:.2f}", xy=(df.index[0], level),
                        fontsize=8, color=COLOR_UP, va="top")

        ax.set_ylabel("价格 (USD)", fontsize=10)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)
        if ma_columns:
            ax.legend(loc="upper left", fontsize=8, ncol=len(ma_columns), framealpha=0.9)

    def _plot_macd(self, ax, df: pd.DataFrame) -> None:
        """绘制 MACD"""
        if not {"MACD_DIF", "MACD_DEA", "MACD_HIST"}.issubset(df.columns):
            ax.text(0.5, 0.5, "MACD 数据不可用", ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color="#9E9E9E")
            ax.set_ylabel("MACD", fontsize=10)
            return

        colors = [COLOR_UP if v >= 0 else COLOR_DOWN for v in df["MACD_HIST"]]
        width = max((df.index[-1] - df.index[0]).days / len(df) * 0.6, 0.3)

        ax.bar(df.index, df["MACD_HIST"], width=width, color=colors, alpha=0.7)
        ax.plot(df.index, df["MACD_DIF"], color="#1976D2", linewidth=1.0, label="DIF")
        ax.plot(df.index, df["MACD_DEA"], color="#F57C00", linewidth=1.0, label="DEA")
        ax.axhline(0, color="#616161", linewidth=0.6)

        ax.set_ylabel("MACD", fontsize=10)
        ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)
        ax.legend(loc="upper left", fontsize=8, ncol=2, framealpha=0.9)

    def _plot_rsi(self, ax, df: pd.DataFrame) -> None:
        """绘制 RSI"""
        if "RSI" not in df.columns:
            ax.text(0.5, 0.5, "RSI 数据不可用", ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color="#9E9E9E")
            ax.set_ylabel("RSI", fontsize=10)
            return

        ax.plot(df.index, df["RSI"], color="#7B1FA2", linewidth=1.2)
        ax.axhline(70, color=COLOR_DOWN, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.axhline(30, color=COLOR_UP, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.fill_between(df.index, 70, 100, color=COLOR_DOWN, alpha=0.06)
        ax.fill_between(df.index, 0, 30, color=COLOR_UP, alpha=0.06)

        ax.set_ylim(0, 100)
        ax.set_yticks([0, 30, 50, 70, 100])
        ax.set_ylabel("RSI", fontsize=10)
        ax.grid(True, color=COLOR_GRID, linewidth=0.5, alpha=0.8)
        ax.set_axisbelow(True)

    def _save(self, fig, symbol: str, timeframe: str) -> Path:
        """保存图片并释放画布"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"{symbol}_{timeframe}_{timestamp}.png"

        fig.savefig(filepath, dpi=self.dpi, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        self.logger.info(f"图表已生成: {filepath}")
        return filepath
