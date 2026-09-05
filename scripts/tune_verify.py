#!/usr/bin/env python3
"""因子权重与持有期调优验证。

方法论：
1. 前 70% 样本做样本内(IS)权重搜索，后 30% 做样本外(OOS)验证
2. 对比基准：当前权重 / 等权 / IS 最优权重 / 反转权重
3. 持有期 1/5/10/20 天分别评估
4. 判据：IS 优势能否在 OOS 复现。不能复现 = 过拟合噪声

结论若为"不能复现"，则不应调参 —— 这正是本脚本要证伪的东西。
"""
import pickle
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PKL = ROOT / ".pytest_tmp" / "factors.pkl"

FACTORS = ["ma_alignment", "macd", "rsi", "bollinger", "multi_period"]
HORIZONS = [1, 5, 10, 20]

CURRENT_W = {
    "ma_alignment": 0.25, "macd": 0.20, "rsi": 0.15,
    "bollinger": 0.15, "multi_period": 0.15,
}
EQUAL_W = {f: 1.0 / len(FACTORS) for f in FACTORS}


def spearman_ic(a: pd.Series, b: pd.Series) -> float:
    """scipy 不可用，用秩相关等价实现。"""
    mask = a.notna() & b.notna()
    if mask.sum() < 30:
        return float("nan")
    return float(a[mask].rank().corr(b[mask].rank()))


def composite(fdf: pd.DataFrame, weights: dict) -> pd.Series:
    """加权合成，对缺失因子做权重重归一化（与 SignalEngine 一致）。"""
    total = pd.Series(0.0, index=fdf.index)
    wsum = pd.Series(0.0, index=fdf.index)
    for f, w in weights.items():
        col = fdf[f]
        valid = col.notna()
        total = total.add((col.fillna(0.0) * w).where(valid, 0.0), fill_value=0.0)
        wsum = wsum.add(pd.Series(w, index=fdf.index).where(valid, 0.0), fill_value=0.0)
    return (total / wsum.replace(0.0, np.nan))


def fwd_return(close: pd.Series, h: int) -> pd.Series:
    return close.shift(-h) / close - 1.0


def weight_grid(step: float = 0.25):
    """在单纯形上枚举权重组合（步长 0.25 → 每因子取 0/.25/.5/.75/1）。"""
    levels = np.arange(0, 1.0001, step)
    for combo in itertools.product(levels, repeat=len(FACTORS)):
        s = sum(combo)
        if s <= 0:
            continue
        yield {f: c / s for f, c in zip(FACTORS, combo)}


def main():
    data = pickle.loads(PKL.read_bytes())
    lines = []

    def emit(s=""):
        print(s)
        lines.append(s)

    for sym, (fdf, close) in data.items():
        emit(f"\n{'='*72}")
        emit(f"  {sym}  样本={len(fdf)}")
        emit(f"{'='*72}")

        split = int(len(fdf) * 0.7)
        emit(f"  样本内 IS: 0..{split}   样本外 OOS: {split}..{len(fdf)}")

        for h in HORIZONS:
            fwd = fwd_return(close, h)
            fdf_is, fwd_is = fdf.iloc[:split], fwd.iloc[:split]
            fdf_oos, fwd_oos = fdf.iloc[split:], fwd.iloc[split:]

            # 基准方案
            schemes = {
                "当前权重": CURRENT_W,
                "等权": EQUAL_W,
            }

            # IS 网格搜索最优
            best_w, best_ic = None, -9.0
            for w in weight_grid(0.25):
                ic = spearman_ic(composite(fdf_is, w), fwd_is)
                if not np.isnan(ic) and ic > best_ic:
                    best_ic, best_w = ic, w
            schemes["IS最优"] = best_w

            emit(f"\n  --- 持有期 {h}d ---")
            emit(f"  {'方案':<10} {'IS_IC':>9} {'OOS_IC':>9}  {'衰减':>8}")
            for name, w in schemes.items():
                ic_is = spearman_ic(composite(fdf_is, w), fwd_is)
                ic_oos = spearman_ic(composite(fdf_oos, w), fwd_oos)
                decay = ic_oos - ic_is
                emit(f"  {name:<10} {ic_is:>+9.4f} {ic_oos:>+9.4f}  {decay:>+8.4f}")

            nz = {f: round(v, 3) for f, v in best_w.items() if v > 0.01}
            emit(f"  IS最优权重: {nz}")

            # 反转检验（对 XAGUSD 尤其相关）
            ic_inv = spearman_ic(-composite(fdf_oos, CURRENT_W), fwd_oos)
            emit(f"  反转信号 OOS_IC: {ic_inv:+.4f}")

    out = ROOT / ".pytest_tmp" / "tune_verify_report.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已写入 {out}")


if __name__ == "__main__":
    main()
