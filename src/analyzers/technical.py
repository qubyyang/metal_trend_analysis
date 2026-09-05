"""
Technical Indicator Calculation Module
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from loguru import logger

from ..utils.exceptions import AnalysisError, ValidationError
from ..utils.common import validate_config, safe_execute
from .signal_engine import SignalEngine


class TechnicalAnalyzer:
    """Technical Analyzer"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Technical Analyzer

        Args:
            config: 技术指标配置

        Raises:
            ValidationError: 配置无效时抛出
        """
        self.logger = logger.bind(name=self.__class__.__name__)

        # 验证配置
        validate_config(config, [], "Technical analyzer config")

        # 指标参数配置，带默认值和验证
        self.ma_config = self._validate_ma_config(config.get('ma', {}))
        self.macd_config = self._validate_macd_config(config.get('macd', {}))
        self.rsi_config = self._validate_rsi_config(config.get('rsi', {}))
        self.bollinger_config = self._validate_bollinger_config(config.get('bollinger', {}))
        self.sr_config = self._validate_sr_config(config.get('support_resistance', {}))

        # 因子化信号引擎：把离散信号聚合为 [-100, +100] 的连续评分
        signal_config = dict(config.get('signal_engine', {}) or {})
        # RSI 阈值与技术指标配置保持一致，避免两套阈值各说各话
        signal_config.setdefault('rsi_overbought', self.rsi_config.get('overbought', 70))
        signal_config.setdefault('rsi_oversold', self.rsi_config.get('oversold', 30))
        self.signal_engine = SignalEngine(signal_config)

        self.logger.info("Technical analyzer initialized with validated parameters")

    def _validate_ma_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证移动平均线配置"""
        periods = config.get('periods', [5, 10, 20, 60])
        if not isinstance(periods, list) or not periods:
            periods = [5, 10, 20, 60]

        # 验证周期值
        validated_periods = []
        for period in periods:
            try:
                period = int(period)
                if period > 0:
                    validated_periods.append(period)
            except (ValueError, TypeError):
                continue

        if not validated_periods:
            validated_periods = [5, 10, 20, 60]

        return {'periods': sorted(validated_periods)}

    def _validate_macd_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证MACD配置"""
        return {
            'fast': max(1, int(config.get('fast', 12))),
            'slow': max(1, int(config.get('slow', 26))),
            'signal': max(1, int(config.get('signal', 9)))
        }

    def _validate_rsi_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证RSI配置"""
        return {
            'period': max(1, int(config.get('period', 14))),
            'overbought': max(50, min(100, int(config.get('overbought', 70)))),
            'oversold': max(0, min(50, int(config.get('oversold', 30))))
        }

    def _validate_bollinger_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证布林带配置"""
        return {
            'period': max(1, int(config.get('period', 20))),
            'std_dev': max(0.1, float(config.get('std_dev', 2.0)))
        }

    def _validate_sr_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证支撑阻力配置"""
        return {
            'lookback': max(10, int(config.get('lookback', 100))),
            'swing_points': max(1, int(config.get('swing_points', 3))),
            'proximity': max(0.001, float(config.get('proximity', 0.01)))
        }

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有技术指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            包含所有指标的 DataFrame

        Raises:
            ValidationError: 数据无效时抛出
            AnalysisError: 计算失败时抛出
        """
        try:
            # 验证输入数据
            self._validate_kline_data(df)

            result_df = df.copy()

            # 计算移动平均线
            ma_data = safe_execute(
                lambda: self.calculate_ma(result_df),
                default_value={},
                logger_name="calculate_ma"
            )

            for period, ma_values in ma_data.items():
                if ma_values is not None:
                    result_df[f'MA{period}'] = ma_values

            # 计算 MACD
            macd_data = safe_execute(
                lambda: self.calculate_macd(result_df),
                default_value={},
                logger_name="calculate_macd"
            )

            if macd_data:
                result_df['MACD_DIF'] = macd_data.get('dif')
                result_df['MACD_DEA'] = macd_data.get('dea')
                result_df['MACD_HIST'] = macd_data.get('hist')

            # 计算 RSI
            rsi_values = safe_execute(
                lambda: self.calculate_rsi(result_df),
                default_value=None,
                logger_name="calculate_rsi"
            )

            if rsi_values is not None:
                result_df['RSI'] = rsi_values

            # 计算布林带
            bb_data = safe_execute(
                lambda: self.calculate_bollinger(result_df),
                default_value={},
                logger_name="calculate_bollinger"
            )

            if bb_data:
                result_df['BB_UPPER'] = bb_data.get('upper')
                result_df['BB_MIDDLE'] = bb_data.get('middle')
                result_df['BB_LOWER'] = bb_data.get('lower')

            # 计算 ATR（波动率，供信号引擎做波动过滤与止损参考）
            atr_values = safe_execute(
                lambda: self.calculate_atr(result_df),
                default_value=None,
                logger_name="calculate_atr"
            )

            if atr_values is not None:
                result_df['ATR'] = atr_values

            # 计算成交量移动平均
            if 'volume' in result_df.columns:
                volume_ma = safe_execute(
                    lambda: result_df['volume'].rolling(window=20).mean(),
                    default_value=None,
                    logger_name="calculate_volume_ma"
                )
                if volume_ma is not None:
                    result_df['VOLUME_MA'] = volume_ma

            self.logger.info(f"Calculated indicators for {len(result_df)} data points")
            return result_df

        except ValidationError:
            raise
        except Exception as e:
            raise AnalysisError(f"Failed to calculate technical indicators: {e}")

    def _validate_kline_data(self, df: pd.DataFrame) -> None:
        """
        验证K线数据

        Args:
            df: K线数据DataFrame

        Raises:
            ValidationError: 数据无效时抛出
        """
        if df is None or df.empty:
            raise ValidationError("K-line data cannot be empty")

        required_columns = ['open', 'high', 'low', 'close']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValidationError(f"Missing required columns: {missing_columns}")

        # 检查数据类型和有效性
        for col in required_columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValidationError(f"Column '{col}' must be numeric")

            if df[col].isna().all():
                raise ValidationError(f"Column '{col}' contains only NaN values")

        # 检查OHLC关系
        if len(df) > 0:
            invalid_ohlc = (
                (df['high'] < df['low']) |
                (df['high'] < df['open']) |
                (df['high'] < df['close']) |
                (df['low'] > df['open']) |
                (df['low'] > df['close'])
            ).any()

            if invalid_ohlc:
                self.logger.warning("Some OHLC relationships are invalid")

    def calculate_ma(self, df: pd.DataFrame) -> Dict[int, pd.Series]:
        """
        计算移动平均线

        Args:
            df: K 线数据 DataFrame

        Returns:
            移动平均线字典 {period: Series}

        Raises:
            AnalysisError: 计算失败时抛出
        """
        try:
            ma_dict = {}

            for period in self.ma_config.get('periods', [5, 10, 20, 60]):
                if len(df) >= period:
                    ma_dict[period] = df['close'].rolling(window=period, min_periods=1).mean()
                else:
                    self.logger.warning(f"Insufficient data for MA({period}), need {period} points, got {len(df)}")
                    ma_dict[period] = pd.Series(index=df.index, dtype=float)

            return ma_dict

        except Exception as e:
            raise AnalysisError(f"Failed to calculate moving averages: {e}")

    def calculate_macd(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算 MACD 指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            MACD 数据字典

        Raises:
            AnalysisError: 计算失败时抛出
        """
        try:
            fast = self.macd_config.get('fast', 12)
            slow = self.macd_config.get('slow', 26)
            signal = self.macd_config.get('signal', 9)

            # 确保fast < slow
            if fast >= slow:
                self.logger.warning(f"MACD fast period ({fast}) should be less than slow period ({slow})")
                fast, slow = min(fast, slow), max(fast, slow)

            if len(df) < slow:
                self.logger.warning(f"Insufficient data for MACD, need {slow} points, got {len(df)}")
                return {
                    'dif': pd.Series(index=df.index, dtype=float),
                    'dea': pd.Series(index=df.index, dtype=float),
                    'hist': pd.Series(index=df.index, dtype=float)
                }

            # 计算EMA
            ema_fast = df['close'].ewm(span=fast, min_periods=1).mean()
            ema_slow = df['close'].ewm(span=slow, min_periods=1).mean()

            # 计算DIF
            dif = ema_fast - ema_slow

            # 计算DEA (DIF的EMA)
            dea = dif.ewm(span=signal, min_periods=1).mean()

            # 计算HIST (柱状图)
            hist = 2 * (dif - dea)

            return {
                'dif': dif,
                'dea': dea,
                'hist': hist
            }

        except Exception as e:
            raise AnalysisError(f"Failed to calculate MACD: {e}")

    def calculate_rsi(self, df: pd.DataFrame) -> pd.Series:
        """
        计算 RSI 指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            RSI 数值序列

        Raises:
            AnalysisError: 计算失败时抛出
        """
        try:
            period = self.rsi_config.get('period', 14)

            if len(df) < period:
                self.logger.warning(f"Insufficient data for RSI, need {period} points, got {len(df)}")
                return pd.Series(index=df.index, dtype=float)

            # 计算价格变化
            close_diff = df['close'].diff()

            # 分离上涨和下跌
            gains = close_diff.where(close_diff > 0, 0.0)
            losses = (-close_diff).where(close_diff < 0, 0.0)

            # 计算平均涨跌幅
            avg_gains = gains.rolling(window=period, min_periods=1).mean()
            avg_losses = losses.rolling(window=period, min_periods=1).mean()

            # 避免除零
            rs = avg_gains / (avg_losses + 1e-10)
            rsi = 100 - (100 / (1 + rs))

            return rsi

        except Exception as e:
            raise AnalysisError(f"Failed to calculate RSI: {e}")

    def calculate_bollinger(self, df: pd.DataFrame) -> Dict[str, pd.Series]:
        """
        计算布林带指标

        Args:
            df: K 线数据 DataFrame

        Returns:
            布林带数据字典

        Raises:
            AnalysisError: 计算失败时抛出
        """
        try:
            period = self.bollinger_config.get('period', 20)
            std_dev = self.bollinger_config.get('std_dev', 2)

            if len(df) < period:
                self.logger.warning(f"Insufficient data for Bollinger Bands, need {period} points, got {len(df)}")
                empty_series = pd.Series(index=df.index, dtype=float)
                return {
                    'upper': empty_series,
                    'middle': empty_series,
                    'lower': empty_series
                }

            # 中轨 (移动平均)
            middle = df['close'].rolling(window=period, min_periods=1).mean()

            # 标准差
            std = df['close'].rolling(window=period, min_periods=1).std()

            # 上下轨
            upper = middle + (std * std_dev)
            lower = middle - (std * std_dev)

            return {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }

        except Exception as e:
            raise AnalysisError(f"Failed to calculate Bollinger Bands: {e}")

    def get_trend_analysis(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        获取趋势分析

        Args:
            df: 包含技术指标的 DataFrame

        Returns:
            趋势分析结果

        Raises:
            AnalysisError: 分析失败时抛出
        """
        try:
            if df.empty:
                raise ValidationError("DataFrame cannot be empty for trend analysis")

            latest = df.iloc[-1]
            trend_signals = []

            # MA趋势分析
            ma_trend = self._analyze_ma_trend(df)
            if ma_trend:
                trend_signals.append(ma_trend)

            # MACD信号
            macd_signal = self._analyze_macd_signal(latest)
            if macd_signal:
                trend_signals.append(macd_signal)

            # RSI信号
            rsi_signal = self._analyze_rsi_signal(latest)

            # 综合趋势判断：由因子化信号引擎给出连续评分
            # 旧实现用 trend_signals.count('bullish') > count('bearish') 投票，
            # 丢失强度信息、无法加权，且会把缺失数据当作中性票稀释信号。
            signal_result = self.signal_engine.evaluate(df)

            if signal_result.get('available'):
                direction = signal_result.get('direction', 'neutral')
                # 向下兼容：通知渠道与报告只识别 bullish/bearish/neutral
                overall_trend = (
                    'bullish' if direction.endswith('bullish')
                    else ('bearish' if direction.endswith('bearish') else 'neutral')
                )
            else:
                # 引擎无可用因子时退回计数法，保证流程不中断
                bullish_signals = trend_signals.count('bullish')
                bearish_signals = trend_signals.count('bearish')
                if bullish_signals > bearish_signals:
                    overall_trend = 'bullish'
                elif bearish_signals > bullish_signals:
                    overall_trend = 'bearish'
                else:
                    overall_trend = 'neutral'

            bullish_signals = trend_signals.count('bullish')
            bearish_signals = trend_signals.count('bearish')

            return {
                'trend': overall_trend,
                'signal_score': signal_result.get('score', 0.0),
                'signal_direction': signal_result.get('direction', 'neutral'),
                'signal_confidence': signal_result.get('confidence', 1.0),
                'signal_detail': signal_result,
                'ma_trend': self._collect_ma_values(latest),
                'ma_signal': ma_trend,
                'ma_alignment': self._check_ma_alignment(latest),
                'macd_signal': macd_signal,
                'rsi': latest.get('RSI'),
                'rsi_signal': rsi_signal,
                'bb_position': self._analyze_bb_position(latest),
                'signals_count': {
                    'bullish': bullish_signals,
                    'bearish': bearish_signals,
                    'neutral': len(trend_signals) - bullish_signals - bearish_signals
                }
            }

        except Exception as e:
            self.logger.error(f"Failed to analyze trend: {e}")
            return {
                'trend': 'neutral',
                'error': str(e)
            }

    def _collect_ma_values(self, latest_data: pd.Series) -> Dict[str, float]:
        """收集最新一根K线上的各周期均线数值"""
        ma_values: Dict[str, float] = {}
        for period in self.ma_config.get('periods', []):
            key = f'MA{period}'
            value = latest_data.get(key)
            if value is not None and not pd.isna(value):
                ma_values[key] = float(value)
        return ma_values

    def _check_ma_alignment(self, latest_data: pd.Series) -> bool:
        """判断均线是否多头排列（短周期均线全部高于长周期均线）"""
        periods = sorted(self.ma_config.get('periods', []))
        values = []
        for period in periods:
            value = latest_data.get(f'MA{period}')
            if value is None or pd.isna(value):
                return False
            values.append(float(value))

        if len(values) < 2:
            return False

        return all(values[i] > values[i + 1] for i in range(len(values) - 1))

    def _analyze_bb_position(self, latest_data: pd.Series) -> str:
        """判断收盘价相对布林带的位置"""
        close = latest_data.get('close')
        upper = latest_data.get('BB_UPPER')
        lower = latest_data.get('BB_LOWER')

        if any(v is None or pd.isna(v) for v in (close, upper, lower)):
            return 'middle'

        if close > upper:
            return 'above_upper'
        if close < lower:
            return 'below_lower'
        return 'middle'

    def _analyze_ma_trend(self, df: pd.DataFrame) -> Optional[str]:
        """分析移动平均线趋势"""
        try:
            if len(df) < 2:
                return None

            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # 检查可用的MA
            ma_columns = [col for col in df.columns if col.startswith('MA')]
            if len(ma_columns) < 2:
                return None

            # 短期MA > 长期MA 且 价格 > 短期MA
            ma_short = f"MA{min(self.ma_config['periods'])}"
            ma_long = f"MA{max(self.ma_config['periods'])}"

            if ma_short not in df.columns or ma_long not in df.columns:
                return None

            current_short = latest[ma_short]
            current_long = latest[ma_long]
            prev_short = prev[ma_short]
            prev_long = prev[ma_long]

            if pd.isna(current_short) or pd.isna(current_long):
                return None

            # 金叉/死叉判断
            if current_short > current_long and prev_short <= prev_long:
                return 'bullish'  # 金叉
            elif current_short < current_long and prev_short >= prev_long:
                return 'bearish'  # 死叉
            elif current_short > current_long:
                return 'bullish'
            elif current_short < current_long:
                return 'bearish'
            else:
                return 'neutral'

        except Exception as e:
            self.logger.warning(f"MA trend analysis failed: {e}")
            return None

    def _analyze_macd_signal(self, latest_data: pd.Series) -> Optional[str]:
        """分析MACD信号"""
        try:
            dif = latest_data.get('MACD_DIF')
            dea = latest_data.get('MACD_DEA')
            hist = latest_data.get('MACD_HIST')

            if pd.isna(dif) or pd.isna(dea) or pd.isna(hist):
                return None

            if dif > dea and hist > 0:
                return 'bullish'
            elif dif < dea and hist < 0:
                return 'bearish'
            else:
                return 'neutral'

        except Exception as e:
            self.logger.warning(f"MACD signal analysis failed: {e}")
            return None

    def _analyze_rsi_signal(self, latest_data: pd.Series) -> Optional[str]:
        """分析RSI信号"""
        try:
            rsi = latest_data.get('RSI')
            if pd.isna(rsi):
                return None

            overbought = self.rsi_config.get('overbought', 70)
            oversold = self.rsi_config.get('oversold', 30)

            if rsi > overbought:
                return 'bearish'  # 超买
            elif rsi < oversold:
                return 'bullish'  # 超卖
            else:
                return 'neutral'

        except Exception as e:
            self.logger.warning(f"RSI signal analysis failed: {e}")
            return None

    def identify_support_resistance(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """
        识别支撑阻力位

        Args:
            df: K线数据DataFrame

        Returns:
            支撑位和阻力位列表的元组

        Raises:
            AnalysisError: 识别失败时抛出
        """
        try:
            if df.empty or len(df) < self.sr_config['lookback']:
                self.logger.warning(f"Insufficient data for S/R analysis, need {self.sr_config['lookback']} points")
                return [], []

            lookback = min(self.sr_config['lookback'], len(df))
            recent_data = df.tail(lookback).copy()

            # 寻找局部高点和低点
            highs, lows = self._find_swing_points(recent_data)

            # 聚类相近的点位
            support_candidates = self._cluster_levels(lows, recent_data['low'].median())
            resistance_candidates = self._cluster_levels(highs, recent_data['high'].median())

            # 按当前价重新归类：支撑必须位于价格下方，阻力必须位于价格上方。
            # 已跌破的支撑会转化为上方阻力，已突破的阻力会转化为下方支撑（角色互换原理）。
            current_price = float(df['close'].iloc[-1])
            all_levels = support_candidates + resistance_candidates

            support_levels = [lv for lv in all_levels if lv < current_price]
            resistance_levels = [lv for lv in all_levels if lv > current_price]

            # 就近排序：第一支撑为最接近现价的下方点位，第一阻力为最接近现价的上方点位
            support_levels = sorted(support_levels, reverse=True)[:5]
            resistance_levels = sorted(resistance_levels)[:5]

            self.logger.debug(f"Identified {len(support_levels)} support and {len(resistance_levels)} resistance levels")
            return support_levels, resistance_levels

        except Exception as e:
            self.logger.error(f"Failed to identify support/resistance: {e}")
            return [], []

    def _find_swing_points(self, df: pd.DataFrame) -> Tuple[List[float], List[float]]:
        """寻找摆动高点和低点"""
        swing_points = self.sr_config.get('swing_points', 3)
        highs = []
        lows = []

        for i in range(swing_points, len(df) - swing_points):
            # 检查是否为局部高点
            if all(df['high'].iloc[i] >= df['high'].iloc[i-j] for j in range(1, swing_points + 1)) and \
               all(df['high'].iloc[i] >= df['high'].iloc[i+j] for j in range(1, swing_points + 1)):
                highs.append(float(df['high'].iloc[i]))

            # 检查是否为局部低点
            if all(df['low'].iloc[i] <= df['low'].iloc[i-j] for j in range(1, swing_points + 1)) and \
               all(df['low'].iloc[i] <= df['low'].iloc[i+j] for j in range(1, swing_points + 1)):
                lows.append(float(df['low'].iloc[i]))

        return highs, lows

    def _cluster_levels(self, levels: List[float], reference_price: float) -> List[float]:
        """聚类相近的价格水平"""
        if not levels:
            return []

        proximity = self.sr_config.get('proximity', 0.01)
        clustered = []

        for level in sorted(levels):
            # 检查是否与已有聚类相近
            merged = False
            for i, cluster in enumerate(clustered):
                if abs(level - cluster) / reference_price <= proximity:
                    # 合并到现有聚类（取平均值）
                    clustered[i] = (cluster + level) / 2
                    merged = True
                    break

            if not merged:
                clustered.append(level)

        return clustered

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        计算平均真实波幅 (ATR)

        Args:
            df: K 线数据 DataFrame
            period: 计算周期

        Returns:
            ATR 数值序列

        Raises:
            AnalysisError: 计算失败时抛出
        """
        try:
            if len(df) < 2:
                self.logger.warning("Insufficient data for ATR calculation")
                return pd.Series(index=df.index, dtype=float)

            high, low, close = df['high'], df['low'], df['close']

            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)

            return tr.rolling(window=period, min_periods=1).mean()

        except Exception as e:
            raise AnalysisError(f"Failed to calculate ATR: {e}")

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
