"""
跨品种联动分析

贵金属价格从来不是孤立的。本模块计算三类跨品种信息：

1. **比价（ratio）**——同一资产类别内部的相对强弱
   - 金银比（XAU/XAG）：历史区间大致 60~90，>85 通常意味着白银
     相对黄金过度低估（或市场处于避险恐慌），<60 则相反。
   - 金铂比（XAU/XPT）：铂金兼具贵金属与工业属性。
   - 金铜比（XAU/HG）：经典的「避险 / 顺周期」跷跷板，
     快速抬升往往对应衰退预期升温。

2. **滚动相关性（rolling correlation）**——用**收益率**而非价格计算。
   直接对价格序列求相关会得到虚假高相关（共同趋势导致的伪回归），
   因此这里一律先转成对数收益率再求相关。

3. **背离检测（divergence）**——当某组合的历史相关性稳定为负
   （如黄金 vs 美元指数），而近期相关性显著偏离历史均值时，
   提示结构性变化，值得人工复核。

设计约束：
- 本模块是**可选增强**。任一辅助品种拉取失败，只跳过涉及它的指标，
  绝不中断主流程（与项目既有的优雅降级原则一致）。
- 所有比价的分子分母顺序在 ``RATIO_DEFINITIONS`` 中显式声明，
  避免出现「金银比」算成「银金比」这类方向性错误。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

# 比价定义：(展示名, 分子品种, 分母品种, 说明)
RATIO_DEFINITIONS: List[Dict[str, str]] = [
    {
        "key": "gold_silver",
        "name": "金银比",
        "numerator": "XAUUSD",
        "denominator": "XAGUSD",
        "note": "衡量白银相对黄金的强弱，历史常见区间 60~90",
    },
    {
        "key": "gold_platinum",
        "name": "金铂比",
        "numerator": "XAUUSD",
        "denominator": "XPTUSD",
        "note": "铂金兼具工业属性，比值走高多反映工业需求走弱",
    },
    {
        "key": "gold_copper",
        "name": "金铜比",
        "numerator": "XAUUSD",
        "denominator": "HGUSD",
        "note": "避险与顺周期的跷跷板，快速抬升对应衰退预期升温",
    },
]

# 关注的相关性组合及其历史先验方向
CORRELATION_PAIRS: List[Dict[str, Any]] = [
    {"a": "XAUUSD", "b": "DXY", "expected": "negative",
     "note": "黄金以美元计价，通常与美元指数负相关"},
    {"a": "XAUUSD", "b": "XAGUSD", "expected": "positive",
     "note": "同为贵金属，通常高度正相关"},
    {"a": "XAUUSD", "b": "CLUSD", "expected": "positive",
     "note": "通胀预期共同驱动，正相关但强度不稳定"},
    {"a": "XAGUSD", "b": "HGUSD", "expected": "positive",
     "note": "白银工业属性使其与铜同步性较强"},
]


class CrossAssetAnalyzer:
    """跨品种比价与相关性分析器"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        # 滚动相关性窗口（交易日）
        self.corr_window = int(self.config.get("correlation_window", 60))
        # 比价的历史分位参考窗口
        self.percentile_window = int(self.config.get("percentile_window", 250))
        # 相关性偏离多少个历史标准差算作背离
        self.divergence_sigma = float(self.config.get("divergence_sigma", 2.0))

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    def _close_series(data: Dict[str, pd.DataFrame], symbol: str) -> Optional[pd.Series]:
        """从数据字典中取出收盘价序列，缺失或过短则返回 None"""
        df = data.get(symbol)
        if df is None or df.empty or "close" not in df.columns:
            return None

        series = pd.to_numeric(df["close"], errors="coerce").dropna()
        return series if len(series) >= 2 else None

    @staticmethod
    def _log_returns(series: pd.Series) -> pd.Series:
        """对数收益率。价格必须为正，非正值会产生 inf/NaN，先行过滤"""
        clean = series[series > 0]
        return np.log(clean).diff().dropna()

    # ------------------------------------------------------------------
    # 比价
    # ------------------------------------------------------------------
    def compute_ratios(self, data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """计算各组比价的当前值、变动与历史分位"""
        results: List[Dict[str, Any]] = []

        for definition in RATIO_DEFINITIONS:
            num = self._close_series(data, definition["numerator"])
            den = self._close_series(data, definition["denominator"])

            if num is None or den is None:
                self.logger.debug(
                    f"{definition['name']} 缺少数据，已跳过 "
                    f"({definition['numerator']}/{definition['denominator']})"
                )
                continue

            # 按日期对齐，避免交易日不一致导致的错位比价
            aligned = pd.concat([num, den], axis=1, join="inner").dropna()
            if len(aligned) < 2:
                continue

            aligned.columns = ["num", "den"]
            aligned = aligned[aligned["den"] > 0]
            if len(aligned) < 2:
                continue

            ratio = aligned["num"] / aligned["den"]
            current = float(ratio.iloc[-1])
            previous = float(ratio.iloc[-2])
            change_pct = ((current - previous) / previous * 100) if previous else 0.0

            window = ratio.tail(self.percentile_window)
            percentile = float((window <= current).mean() * 100) if len(window) else np.nan

            results.append({
                "key": definition["key"],
                "name": definition["name"],
                "pair": f"{definition['numerator']}/{definition['denominator']}",
                "value": current,
                "change_percent": change_pct,
                "percentile": percentile,
                "window_high": float(window.max()) if len(window) else np.nan,
                "window_low": float(window.min()) if len(window) else np.nan,
                "sample_size": int(len(window)),
                "note": definition["note"],
            })

        return results

    # ------------------------------------------------------------------
    # 相关性
    # ------------------------------------------------------------------
    def compute_correlations(self, data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """计算各关注组合的滚动相关性及其相对历史的偏离"""
        results: List[Dict[str, Any]] = []

        for pair in CORRELATION_PAIRS:
            sa = self._close_series(data, pair["a"])
            sb = self._close_series(data, pair["b"])
            if sa is None or sb is None:
                continue

            ra = self._log_returns(sa)
            rb = self._log_returns(sb)
            aligned = pd.concat([ra, rb], axis=1, join="inner").dropna()
            if len(aligned) < self.corr_window + 5:
                self.logger.debug(
                    f"{pair['a']}~{pair['b']} 重叠样本不足 "
                    f"({len(aligned)} < {self.corr_window + 5})，已跳过"
                )
                continue

            aligned.columns = ["a", "b"]
            rolling = aligned["a"].rolling(self.corr_window).corr(aligned["b"]).dropna()
            if rolling.empty:
                continue

            current = float(rolling.iloc[-1])
            hist_mean = float(rolling.mean())
            hist_std = float(rolling.std())

            # 背离判定：偏离历史均值超过 N 个标准差
            z_score = ((current - hist_mean) / hist_std) if hist_std > 1e-9 else 0.0
            diverged = abs(z_score) >= self.divergence_sigma

            # 是否偏离历史先验方向
            sign_flipped = (
                (pair["expected"] == "negative" and current > 0.1)
                or (pair["expected"] == "positive" and current < -0.1)
            )

            results.append({
                "pair": f"{pair['a']}~{pair['b']}",
                "symbol_a": pair["a"],
                "symbol_b": pair["b"],
                "correlation": current,
                "historical_mean": hist_mean,
                "historical_std": hist_std,
                "z_score": z_score,
                "diverged": bool(diverged),
                "sign_flipped": bool(sign_flipped),
                "expected": pair["expected"],
                "window": self.corr_window,
                "sample_size": int(len(aligned)),
                "note": pair["note"],
            })

        return results

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    def analyze(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """执行完整的跨品种分析

        Args:
            data: {通用品种代码: 日线 DataFrame}

        Returns:
            含 ratios / correlations / alerts / available 的结果字典。
            任何子项失败都只影响该子项，不抛出异常。
        """
        if not data:
            return {"available": False, "reason": "无可用品种数据",
                    "ratios": [], "correlations": [], "alerts": []}

        try:
            ratios = self.compute_ratios(data)
        except Exception as e:  # pragma: no cover - 防御性兜底
            self.logger.error(f"比价计算失败: {e}")
            ratios = []

        try:
            correlations = self.compute_correlations(data)
        except Exception as e:  # pragma: no cover
            self.logger.error(f"相关性计算失败: {e}")
            correlations = []

        alerts = self._build_alerts(ratios, correlations)

        return {
            "available": bool(ratios or correlations),
            "symbols": sorted(data.keys()),
            "ratios": ratios,
            "correlations": correlations,
            "alerts": alerts,
        }

    def _build_alerts(
        self,
        ratios: List[Dict[str, Any]],
        correlations: List[Dict[str, Any]],
    ) -> List[str]:
        """把数值结果翻译成可读的提示"""
        alerts: List[str] = []

        for r in ratios:
            pct = r.get("percentile")
            if pct is None or np.isnan(pct):
                continue
            if pct >= 90:
                alerts.append(
                    f"{r['name']} {r['value']:.2f} 处于近 {r['sample_size']} 日的 "
                    f"{pct:.0f}% 分位（偏高）——{r['note']}"
                )
            elif pct <= 10:
                alerts.append(
                    f"{r['name']} {r['value']:.2f} 处于近 {r['sample_size']} 日的 "
                    f"{pct:.0f}% 分位（偏低）——{r['note']}"
                )

        for c in correlations:
            if c.get("sign_flipped"):
                alerts.append(
                    f"{c['pair']} 相关性 {c['correlation']:+.2f}，"
                    f"与历史先验方向（{c['expected']}）相反，结构或已变化"
                )
            elif c.get("diverged"):
                alerts.append(
                    f"{c['pair']} 相关性 {c['correlation']:+.2f} 偏离历史均值 "
                    f"{c['historical_mean']:+.2f} 达 {c['z_score']:+.1f}σ"
                )

        return alerts
