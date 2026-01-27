"""
Technical Indicator Calculation Module
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


class TechnicalAnalyzer:
    """Technical Analyzer"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Technical Analyzer

        Args:
            config: 技术指标配置
        """
        self.ma_config = config.get('ma', {'periods': [5, 10, 20, 60]})
        self.macd_config = config.get('macd', {'fast': 12, 'slow': 26, 'signal': 9})
        self.rsi_config = config.get('rsi', {'period': 14, 'overbought': 70, 'oversold': 30})
        self.bollinger_config = config.get('bollinger', {'period': 20, 'std_dev': 2})

        self.sr_config = config.get('support_resistance', {
            'lookback': 100,
            'swing_points': 3,
            'proximity': 0.01
        })

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            包含所有指标的 DataFrame
        """
        result_df = df.copy()

        # 计算移动平均线
        ma_data = self.calculate_ma(result_df)
        for period, ma_values in ma_data.items():
            result_df[f'MA{period}'] = ma_values

        # 计算 MACD
        macd_data = self.calculate_macd(result_df)
        result_df['MACD_DIF'] = macd_data['dif']
        result_df['MACD_DEA'] = macd_data['dea']
        result_df['MACD_HIST'] = macd_data['hist']

        # 计算 RSI
        rsi_values = self.calculate_rsi(result_df)
        result_df['RSI'] = rsi_values

        # 计算布林带
        bb_data = self.calculate_bollinger(result_df)
        result_df['BB_UPPER'] = bb_data['upper']
        result_df['BB_MIDDLE'] = bb_data['middle']
        result_df['BB_LOWER'] = bb_data['lower']

        # 计算成交量移动平均
        if 'volume' in result_df.columns:
            result_df['VOLUME_MA'] = result_df['volume'].rolling(window=20).mean()

        return result_df

    def calculate_ma(self, df: pd.DataFrame) -> Dict[int, pd.Series]:
        """
        计算移动平均线

        Args:
            df: K 线数据 DataFrame

        Returns:
            移动平均线字典 {period: Series}
        """
        ma_dict = {}

        for period in self.ma_config.get('periods', [5, 10, 20, 60]):
            ma_dict[period] = df['close'].rolling(window=period).mean()

        return ma_dict

    def calculate_macd(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算 MACD 指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            MACD 数据字典
        """
        fast = self.macd_config.get('fast', 12)
        slow = self.macd_config.get('slow', 26)
        signal = self.macd_config.get('signal', 9)

        # 计算 EMA
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()

        # 计算 DIF
        dif = ema_fast - ema_slow

        # 计算 DEA (信号线)
        dea = dif.ewm(span=signal, adjust=False).mean()

        # 计算柱状图
        hist = (dif - dea) * 2

        return {
            'dif': dif,
            'dea': dea,
            'hist': hist
        }

    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 RSI 指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            RSI 值 Series
        """
        period = self.rsi_config.get('period', 14)

        # 计算价格变化
        delta = df['close'].diff()

        # 分离涨跌
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # 计算 RSI
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def calculate_bollinger(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算布林带

        Args:
            df: K 线数据 DataFrame

        Returns:
            布林带数据字典
        """
        period = self.bollinger_config.get('period', 20)
        std_dev = self.bollinger_config.get('std_dev', 2)

        # 中轨（移动平均）
        middle = df['close'].rolling(window=period).mean()

        # 标准差
        std = df['close'].rolling(window=period).std()

        # 上轨和下轨
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算平均真实波幅 (ATR)

        Args:
            df: K 线数据 DataFrame
            period: 计算周期

        Returns:
            ATR 值 Series
        """
        high = df['high']
        low = df['low']
        close = df['close']

        # 计算真实波幅
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # 计算 ATR
        atr = tr.rolling(window=period).mean()

        return atr

    def identify_support_resistance(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """
        识别支撑位和阻力位

        Args:
            df: K 线数据 DataFrame

        Returns:
            (支撑位列表, 阻力位列表)
        """
        lookback = self.sr_config.get('lookback', 100)
        swing_points = self.sr_config.get('swing_points', 3)
        proximity = self.sr_config.get('proximity', 0.01)

        # 获取最近的数据
        recent_df = df.tail(lookback)

        # 寻找局部高点和低点
        highs = []
        lows = []

        for i in range(swing_points, len(recent_df) - swing_points):
            # 局部高点
            is_high = all(
                recent_df.iloc[i]['high'] >= recent_df.iloc[j]['high']
                for j in range(i - swing_points, i + swing_points + 1)
                if j != i
            )

            # 局部低点
            is_low = all(
                recent_df.iloc[i]['low'] <= recent_df.iloc[j]['low']
                for j in range(i - swing_points, i + swing_points + 1)
                if j != i
            )

            if is_high:
                highs.append(recent_df.iloc[i]['high'])
            if is_low:
                lows.append(recent_df.iloc[i]['low'])

        # 合并相近的价格点
        def merge_levels(levels: List[float], proximity: float) -> List[float]:
            if not levels:
                return []

            levels.sort(reverse=True)
            merged = [levels[0]]

            for level in levels[1:]:
                # 检查是否与已存在的点位相近
                is_close = any(
                    abs(level - existing) / existing < proximity
                    for existing in merged
                )

                if not is_close:
                    merged.append(level)

            return merged

        support_levels = merge_levels(lows, proximity)
        resistance_levels = merge_levels(highs, proximity)

        return support_levels, resistance_levels

    def get_trend_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        获取趋势分析结果

        Args:
            df: 包含技术指标的 DataFrame

        Returns:
            趋势分析字典
        """
        if len(df) < 20:
            return {'error': '数据不足'}

        # 获取最新数据
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # MA 趋势分析
        ma_periods = self.ma_config.get('periods', [5, 10, 20, 60])
        ma_trend = {}
        ma_alignment = True  # 是否多头排列

        for period in ma_periods:
            ma_key = f'MA{period}'
            if ma_key in df.columns:
                ma_trend[ma_key] = latest[ma_key]
                # 检查多头排列：短期 > 长期
                if period < ma_periods[-1]:
                    next_ma_key = f'MA{ma_periods[ma_periods.index(period) + 1]}'
                    if next_ma_key in df.columns:
                        if latest[ma_key] < latest[next_ma_key]:
                            ma_alignment = False

        # MACD 信号
        macd_signal = 'neutral'
        if 'MACD_DIF' in df.columns and 'MACD_DEA' in df.columns:
            if latest['MACD_DIF'] > latest['MACD_DEA'] and prev['MACD_DIF'] <= prev['MACD_DEA']:
                macd_signal = 'golden_cross'  # 金叉
            elif latest['MACD_DIF'] < latest['MACD_DEA'] and prev['MACD_DIF'] >= prev['MACD_DEA']:
                macd_signal = 'death_cross'  # 死叉
            elif latest['MACD_DIF'] > latest['MACD_DEA']:
                macd_signal = 'bullish'  # 多头
            else:
                macd_signal = 'bearish'  # 空头

        # RSI 信号
        rsi_signal = 'neutral'
        if 'RSI' in df.columns:
            rsi_value = latest['RSI']
            overbought = self.rsi_config.get('overbought', 70)
            oversold = self.rsi_config.get('oversold', 30)

            if rsi_value > overbought:
                rsi_signal = 'overbought'
            elif rsi_value < oversold:
                rsi_signal = 'oversold'
            else:
                rsi_signal = 'normal'

        # 布林带位置
        bb_position = 'middle'
        if all(col in df.columns for col in ['BB_UPPER', 'BB_MIDDLE', 'BB_LOWER']):
            if latest['close'] > latest['BB_UPPER']:
                bb_position = 'above_upper'
            elif latest['close'] < latest['BB_LOWER']:
                bb_position = 'below_lower'

        # 综合趋势判断
        trend = 'neutral'
        if ma_alignment and macd_signal in ['golden_cross', 'bullish']:
            trend = 'bullish'
        elif not ma_alignment and macd_signal in ['death_cross', 'bearish']:
            trend = 'bearish'

        return {
            'ma_trend': ma_trend,
            'ma_alignment': ma_alignment,
            'macd_signal': macd_signal,
            'rsi_signal': rsi_signal,
            'bb_position': bb_position,
            'trend': trend
        }

    def save_indicators(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """
        保存指标数据到文件

        Args:
            df: 包含指标的 DataFrame
            symbol: 交易品种代码
            timeframe: 时间周期
        """
        output_dir = Path('data/processed')
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{symbol}_{timeframe}_indicators_{timestamp}.csv"
        filepath = output_dir / filename

        df.to_csv(filepath)
        return filepath
