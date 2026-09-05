"""
因子化信号引擎

替代原先「数信号个数投票」的做法（`count('bullish') > count('bearish')`），
把各技术因子转成 **[-1, +1] 的连续强度**，再加权聚合为
**[-100, +100] 的综合评分**。

这样做解决三个具体问题：

1. **强度信息丢失**。旧逻辑里 RSI=71 与 RSI=95 都只是一个 "bearish"，
   但后者的超买程度远甚于前者。连续打分保留了这一差异。
2. **权重缺失**。趋势类因子（均线排列）与摆动类因子（RSI）在不同市场
   状态下的可靠性并不相同，简单计数等于强行赋予相同权重。
3. **无效因子污染**。若某因子数据缺失（如新浪数据源的 volume 恒为 0），
   旧逻辑会把它算作 "neutral" 参与投票，等于用噪声稀释了有效信号。
   本引擎的做法是**剔除该因子并重新归一化剩余权重**，详见 `_aggregate`。

因子清单：

| 因子 | 默认权重 | 说明 |
|------|---------|------|
| ma_alignment  | 0.25 | 均线多空排列与价格相对均线的位置 |
| macd          | 0.20 | 柱状体方向与 DIF/DEA 相对零轴位置 |
| rsi           | 0.15 | 偏离中枢 50 的程度，超买超卖反向计分 |
| bollinger     | 0.15 | 价格在通道内的相对位置（%B） |
| multi_period  | 0.15 | 日线与周线趋势是否共振 |
| volume        | 0.10 | 量能相对均量的确认强度 |

ATR 不作为方向因子，而是作为**波动率闸门**：波动极端放大时，
技术信号的可靠性下降，对最终评分施加衰减（见 `_volatility_gate`）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

# 默认因子权重。总和为 1.0，但代码不依赖这一点——
# `_aggregate` 会按实际参与的因子重新归一化。
DEFAULT_WEIGHTS: Dict[str, float] = {
    "ma_alignment": 0.25,
    "macd": 0.20,
    "rsi": 0.15,
    "bollinger": 0.15,
    "multi_period": 0.15,
    "volume": 0.10,
}

# 综合评分 -> 方向标签的分界
STRONG_THRESHOLD = 40.0
WEAK_THRESHOLD = 15.0


class FactorScore:
    """单个因子的打分结果

    ``valid=False`` 表示该因子因数据缺失或无效而未参与计算，
    聚合时会被剔除并重新分配权重，而不是当作中性值稀释信号。
    """

    __slots__ = ("name", "score", "valid", "weight", "detail")

    def __init__(
        self,
        name: str,
        score: float = 0.0,
        valid: bool = True,
        weight: float = 0.0,
        detail: str = "",
    ):
        self.name = name
        # 强度一律裁剪到 [-1, 1]，防止个别因子越界主导评分
        self.score = float(np.clip(score, -1.0, 1.0)) if valid else 0.0
        self.valid = bool(valid)
        self.weight = float(weight)
        self.detail = detail

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "valid": self.valid,
            "weight": self.weight,
            "detail": self.detail,
        }

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        state = f"{self.score:+.2f}" if self.valid else "n/a"
        return f"<FactorScore {self.name}={state} w={self.weight:.2f}>"


class SignalEngine:
    """把离散技术信号聚合为加权综合评分"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logger.bind(name=self.__class__.__name__)

        weights = dict(DEFAULT_WEIGHTS)
        weights.update(self.config.get("weights", {}) or {})
        # 负权重没有语义，直接剔除，避免配置笔误导致信号反向
        self.weights = {k: float(v) for k, v in weights.items() if float(v) > 0}

        self.rsi_overbought = float(self.config.get("rsi_overbought", 70))
        self.rsi_oversold = float(self.config.get("rsi_oversold", 30))

        # 波动率闸门：ATR/价格 超过该比例后开始衰减评分
        self.atr_ratio_threshold = float(self.config.get("atr_ratio_threshold", 0.03))
        self.max_volatility_damping = float(
            self.config.get("max_volatility_damping", 0.5)
        )

        self.strong_threshold = float(
            self.config.get("strong_threshold", STRONG_THRESHOLD)
        )
        self.weak_threshold = float(self.config.get("weak_threshold", WEAK_THRESHOLD))

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _get(row: pd.Series, key: str) -> Optional[float]:
        """安全取值：缺列、NaN、非数值一律返回 None"""
        if key not in row.index:
            return None
        value = row.get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return None if not np.isfinite(value) else value

    def _w(self, name: str) -> float:
        return self.weights.get(name, 0.0)

    # ------------------------------------------------------------------
    # 因子：均线排列
    # ------------------------------------------------------------------
    def _factor_ma_alignment(self, row: pd.Series) -> FactorScore:
        """均线因子

        综合两部分：
        - **排列**：短周期均线依次高于长周期为多头排列，反之为空头；
          按相邻均线间的顺序一致比例打分，而非非黑即白。
        - **位置**：收盘价相对最长周期均线的偏离方向。
        """
        weight = self._w("ma_alignment")
        ma_cols = sorted(
            (c for c in row.index if str(c).startswith("MA") and str(c)[2:].isdigit()),
            key=lambda c: int(str(c)[2:]),
        )
        values = [(c, self._get(row, c)) for c in ma_cols]
        values = [(c, v) for c, v in values if v is not None]

        close = self._get(row, "close")
        if len(values) < 2 or close is None:
            return FactorScore(
                "ma_alignment", valid=False, weight=weight,
                detail="均线数据不足（需至少 2 条有效均线）",
            )

        # 相邻均线的排列一致性：短 > 长 记 +1，短 < 长 记 -1
        pairs = list(zip(values, values[1:]))
        votes = [1.0 if a[1] > b[1] else -1.0 for a, b in pairs]
        alignment = sum(votes) / len(votes)

        # 价格相对最长均线的位置
        longest = values[-1][1]
        position = 1.0 if close > longest else -1.0

        score = 0.7 * alignment + 0.3 * position

        if alignment == 1.0:
            shape = "完全多头排列"
        elif alignment == -1.0:
            shape = "完全空头排列"
        else:
            shape = "均线交织"

        detail = (
            f"{shape}（排列一致度 {alignment:+.2f}），"
            f"收盘 {close:.2f} {'高于' if position > 0 else '低于'} "
            f"{values[-1][0]} {longest:.2f}"
        )
        return FactorScore("ma_alignment", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 因子：MACD
    # ------------------------------------------------------------------
    def _factor_macd(self, row: pd.Series) -> FactorScore:
        """MACD 因子：柱状体方向为主，DIF/DEA 相对零轴为辅"""
        weight = self._w("macd")
        dif = self._get(row, "MACD_DIF")
        dea = self._get(row, "MACD_DEA")
        hist = self._get(row, "MACD_HIST")

        if dif is None or dea is None:
            return FactorScore(
                "macd", valid=False, weight=weight, detail="MACD 数据缺失",
            )

        # 金叉/死叉方向
        cross = 1.0 if dif > dea else -1.0
        # 零轴位置：双线在零轴上方强化多头，反之强化空头
        axis = 1.0 if (dif > 0 and dea > 0) else (-1.0 if (dif < 0 and dea < 0) else 0.0)

        score = 0.6 * cross + 0.4 * axis

        hist_text = f"，柱状体 {hist:+.4f}" if hist is not None else ""
        detail = (
            f"DIF {dif:+.4f} {'>' if cross > 0 else '<'} DEA {dea:+.4f}"
            f"（{'金叉' if cross > 0 else '死叉'}状态），"
            f"{'零轴上方' if axis > 0 else ('零轴下方' if axis < 0 else '零轴附近')}"
            f"{hist_text}"
        )
        return FactorScore("macd", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 因子：RSI
    # ------------------------------------------------------------------
    def _factor_rsi(self, row: pd.Series) -> FactorScore:
        """RSI 因子

        注意方向语义：RSI 是**摆动指标**，超买区给出的是看跌提示、
        超卖区给出的是看涨提示，与趋势类因子的方向逻辑相反。
        中枢 50 附近按偏离度线性给分，进入超买超卖区后反向。
        """
        weight = self._w("rsi")
        rsi = self._get(row, "RSI")

        if rsi is None:
            return FactorScore("rsi", valid=False, weight=weight, detail="RSI 数据缺失")

        if rsi >= self.rsi_overbought:
            # 超买越深，看跌强度越大；70->-0.5，100->-1.0
            depth = (rsi - self.rsi_overbought) / max(100 - self.rsi_overbought, 1e-9)
            score = -0.5 - 0.5 * min(depth, 1.0)
            state = "超买"
        elif rsi <= self.rsi_oversold:
            depth = (self.rsi_oversold - rsi) / max(self.rsi_oversold, 1e-9)
            score = 0.5 + 0.5 * min(depth, 1.0)
            state = "超卖"
        else:
            # 中性区：按相对 50 的偏离给出弱趋势倾向，最大 ±0.5
            span = max(self.rsi_overbought - 50, 50 - self.rsi_oversold, 1e-9)
            score = 0.5 * ((rsi - 50) / span)
            state = "中性区"

        detail = f"RSI {rsi:.1f}（{state}，阈值 {self.rsi_oversold:.0f}/{self.rsi_overbought:.0f}）"
        return FactorScore("rsi", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 因子：布林带
    # ------------------------------------------------------------------
    def _factor_bollinger(self, row: pd.Series) -> FactorScore:
        """布林带因子：用 %B 衡量价格在通道内的相对位置

        %B = (close - lower) / (upper - lower)
        0.5 为中轨，>1 突破上轨，<0 跌破下轨。

        这里按**趋势跟随**语义处理：贴近上轨视为强势。
        与 RSI 的反转语义形成互补，两者在极端行情下会相互抵消，
        这是设计意图——单边行情中不应由单一因子独断。
        """
        weight = self._w("bollinger")
        upper = self._get(row, "BB_UPPER")
        lower = self._get(row, "BB_LOWER")
        close = self._get(row, "close")

        if upper is None or lower is None or close is None:
            return FactorScore(
                "bollinger", valid=False, weight=weight, detail="布林带数据缺失",
            )

        width = upper - lower
        if width <= 1e-9:
            # 通道收缩到零宽（数据异常或极端横盘），无法给出有意义的位置
            return FactorScore(
                "bollinger", valid=False, weight=weight,
                detail="布林带通道宽度为零，无法定位",
            )

        percent_b = (close - lower) / width
        # %B 0~1 映射到 -1~+1，越界部分自然溢出后由 FactorScore 裁剪
        score = 2.0 * percent_b - 1.0

        if percent_b > 1:
            state = "突破上轨"
        elif percent_b < 0:
            state = "跌破下轨"
        elif percent_b >= 0.8:
            state = "贴近上轨"
        elif percent_b <= 0.2:
            state = "贴近下轨"
        else:
            state = "通道中部"

        detail = f"%B {percent_b:.2f}（{state}，通道 {lower:.2f}~{upper:.2f}）"
        return FactorScore("bollinger", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 因子：成交量确认
    # ------------------------------------------------------------------
    def _factor_volume(self, df: pd.DataFrame, row: pd.Series) -> FactorScore:
        """成交量因子：放量确认价格方向，缩量削弱信号

        **重要**：新浪财经的贵金属接口 volume 字段恒为 0
        （现货金银无集中交易所，没有统一成交量口径）。
        此时必须把因子标记为 invalid 并让出权重，
        否则「恒为 0 的成交量」会被当作「持续缩量」，
        变成一个稳定输出负分的噪声源，系统性压低所有多头信号。

        判定无效的条件：最近窗口内成交量全为 0 或全部缺失。
        """
        weight = self._w("volume")

        if "volume" not in df.columns:
            return FactorScore(
                "volume", valid=False, weight=weight, detail="无成交量字段",
            )

        recent = pd.to_numeric(df["volume"].tail(60), errors="coerce").dropna()
        if recent.empty or float(recent.abs().sum()) <= 0:
            return FactorScore(
                "volume", valid=False, weight=weight,
                detail="成交量恒为 0（现货金银无统一成交量口径），因子已剔除",
            )

        volume = self._get(row, "volume")
        volume_ma = self._get(row, "VOLUME_MA")
        close = self._get(row, "close")

        if volume is None or close is None:
            return FactorScore(
                "volume", valid=False, weight=weight, detail="成交量数据缺失",
            )

        if volume_ma is None or volume_ma <= 0:
            volume_ma = float(recent.mean())
        if volume_ma <= 0:
            return FactorScore(
                "volume", valid=False, weight=weight, detail="均量为零，无法比较",
            )

        # 价格方向：与前一根收盘比较
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(closes) < 2:
            return FactorScore(
                "volume", valid=False, weight=weight, detail="收盘数据不足",
            )
        direction = 1.0 if closes.iloc[-1] >= closes.iloc[-2] else -1.0

        # 量比 -> 确认强度：1 倍均量为中性，2 倍及以上为满强度
        ratio = volume / volume_ma
        strength = float(np.clip((ratio - 1.0), -1.0, 1.0))

        score = direction * strength

        detail = (
            f"量比 {ratio:.2f}（{'放量' if ratio > 1 else '缩量'}），"
            f"价格{'上涨' if direction > 0 else '下跌'}，"
            f"确认强度 {score:+.2f}"
        )
        return FactorScore("volume", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 因子：多周期共振
    # ------------------------------------------------------------------
    def _factor_multi_period(
        self, df: pd.DataFrame, weekly_df: Optional[pd.DataFrame] = None
    ) -> FactorScore:
        """多周期共振：日线与周线趋势方向是否一致

        周线数据若未显式传入，则由日线重采样得到（W-FRI）。
        趋势方向用「收盘价相对自身均线」判定，两个周期同向时给满分，
        背离时给相反的弱分——高周期趋势的权重更高，因此以周线为准。
        """
        weight = self._w("multi_period")

        closes = pd.to_numeric(df["close"], errors="coerce").dropna() if "close" in df.columns else pd.Series(dtype=float)
        if len(closes) < 20:
            return FactorScore(
                "multi_period", valid=False, weight=weight,
                detail="日线样本不足 20 根，无法判定多周期共振",
            )

        if weekly_df is not None and not weekly_df.empty and "close" in weekly_df.columns:
            weekly_closes = pd.to_numeric(weekly_df["close"], errors="coerce").dropna()
        else:
            try:
                weekly_closes = closes.resample("W-FRI").last().dropna()
            except (TypeError, ValueError):
                # 索引非时间类型时无法重采样
                return FactorScore(
                    "multi_period", valid=False, weight=weight,
                    detail="索引非时间类型，无法重采样为周线",
                )

        if len(weekly_closes) < 10:
            return FactorScore(
                "multi_period", valid=False, weight=weight,
                detail=f"周线样本不足 10 根（当前 {len(weekly_closes)}）",
            )

        daily_ma = closes.rolling(20).mean().iloc[-1]
        weekly_ma = weekly_closes.rolling(10).mean().iloc[-1]

        if not np.isfinite(daily_ma) or not np.isfinite(weekly_ma):
            return FactorScore(
                "multi_period", valid=False, weight=weight, detail="均线计算结果无效",
            )

        daily_dir = 1.0 if closes.iloc[-1] > daily_ma else -1.0
        weekly_dir = 1.0 if weekly_closes.iloc[-1] > weekly_ma else -1.0

        if daily_dir == weekly_dir:
            score = daily_dir
            state = "共振"
        else:
            # 背离时以周线方向为准，但强度减半
            score = 0.5 * weekly_dir
            state = "背离（以周线为准）"

        detail = (
            f"日线{'多' if daily_dir > 0 else '空'}头 / "
            f"周线{'多' if weekly_dir > 0 else '空'}头，{state}"
        )
        return FactorScore("multi_period", score, True, weight, detail)

    # ------------------------------------------------------------------
    # 波动率闸门
    # ------------------------------------------------------------------
    def _volatility_gate(self, row: pd.Series) -> Dict[str, Any]:
        """基于 ATR/价格 比率计算评分衰减系数

        逻辑：波动率越高，同样的技术形态越容易被噪声推翻，
        因此对综合评分乘以一个 <= 1 的衰减系数。
        这不改变方向，只降低置信度——方向判断本身仍由因子决定。

        Returns:
            含 damping（衰减系数）、atr_ratio、detail 的字典
        """
        atr = self._get(row, "ATR")
        close = self._get(row, "close")

        if atr is None or close is None or close <= 0:
            return {"damping": 1.0, "atr_ratio": None,
                    "detail": "ATR 不可用，未施加波动率衰减"}

        atr_ratio = atr / close

        if atr_ratio <= self.atr_ratio_threshold:
            return {"damping": 1.0, "atr_ratio": atr_ratio,
                    "detail": f"ATR/价格 {atr_ratio:.2%}，波动正常，无衰减"}

        # 超出阈值后线性衰减，最多衰减到 max_volatility_damping
        excess = (atr_ratio - self.atr_ratio_threshold) / self.atr_ratio_threshold
        damping = max(
            self.max_volatility_damping,
            1.0 - excess * (1.0 - self.max_volatility_damping),
        )
        return {
            "damping": damping,
            "atr_ratio": atr_ratio,
            "detail": (
                f"ATR/价格 {atr_ratio:.2%} 超过阈值 "
                f"{self.atr_ratio_threshold:.2%}，置信度衰减至 {damping:.0%}"
            ),
        }

    # ------------------------------------------------------------------
    # 聚合
    # ------------------------------------------------------------------
    @staticmethod
    def _aggregate(factors: List[FactorScore]) -> Dict[str, Any]:
        """按有效因子的权重加权平均

        关键点：只用 **valid 因子** 的权重做分母。
        若把无效因子也计入分母，等价于给它们塞了 0 分，
        会把综合评分朝中性方向拉，属于隐性的信号稀释。
        """
        valid = [f for f in factors if f.valid and f.weight > 0]
        total_weight = sum(f.weight for f in valid)

        if not valid or total_weight <= 0:
            return {"raw_score": 0.0, "total_weight": 0.0, "valid_count": 0}

        weighted = sum(f.score * f.weight for f in valid)
        return {
            "raw_score": weighted / total_weight,
            "total_weight": total_weight,
            "valid_count": len(valid),
        }

    def _label(self, score: float) -> str:
        """综合评分 -> 方向标签"""
        if score >= self.strong_threshold:
            return "strong_bullish"
        if score >= self.weak_threshold:
            return "bullish"
        if score <= -self.strong_threshold:
            return "strong_bearish"
        if score <= -self.weak_threshold:
            return "bearish"
        return "neutral"

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------
    def evaluate(
        self,
        df: pd.DataFrame,
        weekly_df: Optional[pd.DataFrame] = None,
    ) -> Dict[str, Any]:
        """计算综合信号评分

        Args:
            df: 已由 TechnicalAnalyzer.calculate_all_indicators 处理过的 DataFrame
            weekly_df: 可选的周线数据；不提供时由日线重采样

        Returns:
            含 score / direction / factors / volatility 的结果字典。
            数据不可用时返回 available=False，不抛异常。
        """
        if df is None or df.empty:
            return {
                "available": False,
                "score": 0.0,
                "direction": "neutral",
                "reason": "无有效 K 线数据",
                "factors": [],
            }

        row = df.iloc[-1]

        factors = [
            self._factor_ma_alignment(row),
            self._factor_macd(row),
            self._factor_rsi(row),
            self._factor_bollinger(row),
            self._factor_multi_period(df, weekly_df),
            self._factor_volume(df, row),
        ]
        # 权重为 0 的因子（被配置关闭）不参与也不展示为"失效"
        factors = [f for f in factors if f.weight > 0]

        agg = self._aggregate(factors)
        volatility = self._volatility_gate(row)

        # raw_score 在 [-1, 1]，放大到 [-100, 100] 后施加波动率衰减
        score = agg["raw_score"] * 100.0 * volatility["damping"]
        score = float(np.clip(score, -100.0, 100.0))

        invalid = [f.name for f in factors if not f.valid]

        return {
            "available": agg["valid_count"] > 0,
            "score": round(score, 2),
            "direction": self._label(score),
            "raw_score": round(agg["raw_score"] * 100.0, 2),
            "confidence": round(volatility["damping"], 3),
            "valid_factors": agg["valid_count"],
            "total_factors": len(factors),
            "excluded_factors": invalid,
            "effective_weight": round(agg["total_weight"], 3),
            "factors": [f.to_dict() for f in factors],
            "volatility": volatility,
        }
