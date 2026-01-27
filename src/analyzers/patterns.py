"""
K 线形态识别模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any


class PatternRecognizer:
    """K 线形态识别器"""

    def __init__(self):
        """初始化形态识别器"""
        pass

    def detect_patterns(self, df: pd.DataFrame, lookback: int = 5) -> Dict[str, List[Dict[str, Any]]]:
        """
        检测所有 K 线形态

        Args:
            df: K 线数据 DataFrame
            lookback: 向前查找的 K 线数量

        Returns:
            形态字典 {pattern_name: list}
        """
        patterns = {
            'doji': [],
            'hammer': [],
            'shooting_star': [],
            'engulfing_bullish': [],
            'engulfing_bearish': [],
            'morning_star': [],
            'evening_star': [],
            'three_white_soldiers': [],
            'three_black_crows': []
        }

        # 检查每条 K 线
        for i in range(1, min(lookback + 1, len(df))):
            current = df.iloc[-i]
            prev = df.iloc[-i-1] if i < len(df) - 1 else None
            prev2 = df.iloc[-i-2] if i < len(df) - 2 else None

            # 十字星
            if self._is_doji(current):
                patterns['doji'].append({
                    'index': df.index[-i],
                    'description': '十字星形态'
                })

            # 锤子线
            if self._is_hammer(current):
                patterns['hammer'].append({
                    'index': df.index[-i],
                    'description': '锤子线形态'
                })

            # 射击之星
            if self._is_shooting_star(current):
                patterns['shooting_star'].append({
                    'index': df.index[-i],
                    'description': '射击之星形态'
                })

            # 吞噬形态
            if prev is not None:
                if self._is_bullish_engulfing(prev, current):
                    patterns['engulfing_bullish'].append({
                        'index': df.index[-i],
                        'description': '看涨吞噬形态'
                    })

                if self._is_bearish_engulfing(prev, current):
                    patterns['engulfing_bearish'].append({
                        'index': df.index[-i],
                        'description': '看跌吞噬形态'
                    })

            # 三星形态
            if prev is not None and prev2 is not None:
                if self._is_morning_star(prev2, prev, current):
                    patterns['morning_star'].append({
                        'index': df.index[-i],
                        'description': '早晨之星形态'
                    })

                if self._is_evening_star(prev2, prev, current):
                    patterns['evening_star'].append({
                        'index': df.index[-i],
                        'description': '黄昏之星形态'
                    })

        # 三白兵和三黑鸦
        if len(df) >= 3:
            last_three = df.iloc[-3:]
            if self._is_three_white_soldiers(last_three):
                patterns['three_white_soldiers'].append({
                    'index': df.index[-1],
                    'description': '三白兵形态'
                })

            if self._is_three_black_crows(last_three):
                patterns['three_black_crows'].append({
                    'index': df.index[-1],
                    'description': '三黑鸦形态'
                })

        return patterns

    def _get_body_size(self, candle: pd.Series) -> float:
        """获取实体大小"""
        return abs(candle['close'] - candle['open'])

    def _get_upper_shadow(self, candle: pd.Series) -> float:
        """获取上影线长度"""
        return candle['high'] - max(candle['close'], candle['open'])

    def _get_lower_shadow(self, candle: pd.Series) -> float:
        """获取下影线长度"""
        return min(candle['close'], candle['open']) - candle['low']

    def _is_bullish(self, candle: pd.Series) -> bool:
        """是否为阳线"""
        return candle['close'] > candle['open']

    def _is_bearish(self, candle: pd.Series) -> bool:
        """是否为阴线"""
        return candle['close'] < candle['open']

    def _is_doji(self, candle: pd.Series, tolerance: float = 0.1) -> bool:
        """
        识别十字星

        Args:
            candle: K 线数据
            tolerance: 实体大小容忍度

        Returns:
            是否为十字星
        """
        body_size = self._get_body_size(candle)
        candle_range = candle['high'] - candle['low']

        if candle_range == 0:
            return False

        body_ratio = body_size / candle_range
        return body_ratio < tolerance

    def _is_hammer(self, candle: pd.Series, shadow_ratio: float = 2.0) -> bool:
        """
        识别锤子线

        Args:
            candle: K 线数据
            shadow_ratio: 下影线与实体的最小比例

        Returns:
            是否为锤子线
        """
        body_size = self._get_body_size(candle)
        lower_shadow = self._get_lower_shadow(candle)
        upper_shadow = self._get_upper_shadow(candle)

        # 下影线长，上影线短或无，实体较小
        if lower_shadow > body_size * shadow_ratio and upper_shadow < body_size:
            return True

        return False

    def _is_shooting_star(self, candle: pd.Series, shadow_ratio: float = 2.0) -> bool:
        """
        识别射击之星

        Args:
            candle: K 线数据
            shadow_ratio: 上影线与实体的最小比例

        Returns:
            是否为射击之星
        """
        body_size = self._get_body_size(candle)
        upper_shadow = self._get_upper_shadow(candle)
        lower_shadow = self._get_lower_shadow(candle)

        # 上影线长，下影线短或无，实体较小
        if upper_shadow > body_size * shadow_ratio and lower_shadow < body_size:
            return True

        return False

    def _is_bullish_engulfing(self, prev: pd.Series, current: pd.Series) -> bool:
        """
        识别看涨吞噬

        Args:
            prev: 前一根 K 线
            current: 当前 K 线

        Returns:
            是否为看涨吞噬
        """
        # 前一根是阴线，当前是阳线
        if not (self._is_bearish(prev) and self._is_bullish(current)):
            return False

        # 当前实体完全吞没前一根实体
        return (current['open'] < prev['close'] and
                current['close'] > prev['open'])

    def _is_bearish_engulfing(self, prev: pd.Series, current: pd.Series) -> bool:
        """
        识别看跌吞噬

        Args:
            prev: 前一根 K 线
            current: 当前 K 线

        Returns:
            是否为看跌吞噬
        """
        # 前一根是阳线，当前是阴线
        if not (self._is_bullish(prev) and self._is_bearish(current)):
            return False

        # 当前实体完全吞没前一根实体
        return (current['open'] > prev['close'] and
                current['close'] < prev['open'])

    def _is_morning_star(self, prev2: pd.Series, prev: pd.Series, current: pd.Series) -> bool:
        """
        识别早晨之星

        Args:
            prev2: 第一根 K 线（大阴线）
            prev: 第二根 K 线（小实体）
            current: 第三根 K 线（大阳线）

        Returns:
            是否为早晨之星
        """
        # 第一根是大阴线
        if not self._is_bearish(prev2):
            return False

        # 第三根是大阳线
        if not self._is_bullish(current):
            return False

        # 第二根是小实体（可能是十字星）
        prev_body = self._get_body_size(prev)
        prev2_body = self._get_body_size(prev2)
        current_body = self._get_body_size(current)

        # 第二根实体较小
        if prev_body > prev2_body * 0.5:
            return False

        # 价格回升超过第一根实体的中点
        midpoint = (prev2['open'] + prev2['close']) / 2
        if current['close'] < midpoint:
            return False

        return True

    def _is_evening_star(self, prev2: pd.Series, prev: pd.Series, current: pd.Series) -> bool:
        """
        识别黄昏之星

        Args:
            prev2: 第一根 K 线（大阳线）
            prev: 第二根 K 线（小实体）
            current: 第三根 K 线（大阴线）

        Returns:
            是否为黄昏之星
        """
        # 第一根是大阳线
        if not self._is_bullish(prev2):
            return False

        # 第三根是大阴线
        if not self._is_bearish(current):
            return False

        # 第二根是小实体（可能是十字星）
        prev_body = self._get_body_size(prev)
        prev2_body = self._get_body_size(prev2)
        current_body = self._get_body_size(current)

        # 第二根实体较小
        if prev_body > prev2_body * 0.5:
            return False

        # 价格下跌超过第一根实体的中点
        midpoint = (prev2['open'] + prev2['close']) / 2
        if current['close'] > midpoint:
            return False

        return True

    def _is_three_white_soldiers(self, three_candles: pd.DataFrame) -> bool:
        """
        识别三白兵

        Args:
            three_candles: 三根 K 线数据

        Returns:
            是否为三白兵
        """
        # 三根都是阳线
        if not all(self._is_bullish(three_candles.iloc[i]) for i in range(3)):
            return False

        # 每根收盘价高于前一根收盘价
        for i in range(1, 3):
            if three_candles.iloc[i]['close'] <= three_candles.iloc[i-1]['close']:
                return False

        # 每根开盘价高于前一根实体内部
        for i in range(1, 3):
            prev = three_candles.iloc[i-1]
            current = three_candles.iloc[i]

            if current['open'] < prev['open'] or current['open'] > prev['close']:
                return False

        return True

    def _is_three_black_crows(self, three_candles: pd.DataFrame) -> bool:
        """
        识别三黑鸦

        Args:
            three_candles: 三根 K 线数据

        Returns:
            是否为三黑鸦
        """
        # 三根都是阴线
        if not all(self._is_bearish(three_candles.iloc[i]) for i in range(3)):
            return False

        # 每根收盘价低于前一根收盘价
        for i in range(1, 3):
            if three_candles.iloc[i]['close'] >= three_candles.iloc[i-1]['close']:
                return False

        # 每根开盘价低于前一根实体内部
        for i in range(1, 3):
            prev = three_candles.iloc[i-1]
            current = three_candles.iloc[i]

            if current['open'] > prev['open'] or current['open'] < prev['close']:
                return False

        return True

    def get_pattern_summary(self, patterns: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        生成形态摘要

        Args:
            patterns: 形态字典

        Returns:
            形态摘要文本
        """
        summary_lines = []

        for pattern_name, pattern_list in patterns.items():
            if pattern_list:
                pattern_cn = {
                    'doji': '十字星',
                    'hammer': '锤子线',
                    'shooting_star': '射击之星',
                    'engulfing_bullish': '看涨吞噬',
                    'engulfing_bearish': '看跌吞噬',
                    'morning_star': '早晨之星',
                    'evening_star': '黄昏之星',
                    'three_white_soldiers': '三白兵',
                    'three_black_crows': '三黑鸦'
                }

                count = len(pattern_list)
                summary_lines.append(f"- {pattern_cn.get(pattern_name, pattern_name)}: {count}次")

        if not summary_lines:
            return "近期未检测到明显的 K 线形态"

        return '\n'.join(summary_lines)
