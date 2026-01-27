"""
iTick API 客户端模块
"""
import requests
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time
from pathlib import Path


class ITickClient:
    """iTick API 客户端"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 iTick 客户端

        Args:
            config: iTick 配置字典
        """
        self.base_url = config.get('base_url', 'https://api.itick.org')
        self.token = config.get('token', '')
        self.timeout = config.get('timeout', 30)
        self.retry = config.get('retry', 3)
        self.retry_delay = config.get('retry_delay', 2)
        self.default_kline_count = config.get('default_kline_count', 200)

        # API 端点
        self.endpoints = config.get('endpoints', {
            'quote': '/quote',
            'kline': '/kline',
            'history': '/history'
        })

        # 请求头（根据官方示例）
        self.headers = {
            'accept': 'application/json',
            'token': self.token
        }

    def _request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发送 API 请求（带重试）

        Args:
            endpoint: API 端点
            params: 请求参数

        Returns:
            响应数据

        Raises:
            Exception: 请求失败
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(self.retry):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    params=params,
                    timeout=self.timeout
                )

                response.raise_for_status()
                data = response.json()

                # 检查响应状态
                if 'code' in data and data['code'] != 0:
                    raise Exception(f"API 错误: {data.get('msg', '未知错误')}")

                return data

            except requests.exceptions.RequestException as e:
                if attempt < self.retry - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise Exception(f"请求失败: {str(e)}")

    def get_quote(self, symbol: str, region: str = 'GB') -> Dict[str, Any]:
        """
        获取实时报价

        Args:
            symbol: 交易品种代码，如 'XAUUSD'
            region: 区域代码，默认 'GB'

        Returns:
            实时报价数据
        """
        params = {
            'code': symbol,
            'region': region
        }

        data = self._request(self.endpoints['quote'], params)

        # 解析报价数据（根据 iTick API 实际返回格式）
        if 'data' in data:
            quote_data = data['data']
            return {
                'symbol': symbol,
                'price': quote_data.get('p'),           # 当前价格
                'change': quote_data.get('ch'),         # 涨跌额
                'change_percent': quote_data.get('chp'), # 涨跌幅
                'high': quote_data.get('h'),            # 最高价
                'low': quote_data.get('l'),             # 最低价
                'open': quote_data.get('o'),            # 开盘价
                'volume': quote_data.get('v'),          # 成交量
                'timestamp': datetime.now().isoformat()
            }

        return {}

    def get_kline(
        self,
        symbol: str,
        timeframe: str = '1m',
        count: Optional[int] = None,
        region: str = 'GB'
    ) -> pd.DataFrame:
        """
        获取 K 线数据

        Args:
            symbol: 交易品种代码
            timeframe: 时间周期 (1m, 5m - iTick API 目前主要支持这两个周期)
            count: K 线数量，默认使用配置值
            region: 区域代码

        Returns:
            K 线数据 DataFrame
        """
        if count is None:
            count = self.default_kline_count

        # 时间周期映射到 kType 参数
        # 注意：iTick API 主要支持 1m 和 5m
        ktype_map = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440, '1w': 10080
        }
        ktype = ktype_map.get(timeframe, 1)  # 默认 1 分钟

        params = {
            'code': symbol,
            'kType': ktype,
            'region': region
        }

        data = self._request(self.endpoints['kline'], params)

        # 解析 K 线数据（根据 iTick API 实际返回格式）
        if 'data' in data and isinstance(data['data'], list):
            kline_list = []

            for item in data['data']:
                # 时间戳是毫秒，需要转换
                ts = item.get('t', 0)
                if ts > 1e12:  # 毫秒时间戳
                    ts = ts / 1000
                kline_list.append({
                    'timestamp': datetime.fromtimestamp(ts),
                    'open': item.get('o'),
                    'high': item.get('h'),
                    'low': item.get('l'),
                    'close': item.get('c'),
                    'volume': item.get('v', 0)
                })

            df = pd.DataFrame(kline_list)
            if not df.empty:
                df.set_index('timestamp', inplace=True)
                df.sort_index(inplace=True)
                # 只返回最近 count 条数据
                if len(df) > count:
                    df = df.tail(count)

            return df

        return pd.DataFrame()

    def get_history(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1d',
        region: str = 'GB'
    ) -> pd.DataFrame:
        """
        获取历史数据

        Args:
            symbol: 交易品种代码
            start_date: 开始日期
            end_date: 结束日期
            timeframe: 时间周期
            region: 区域代码

        Returns:
            历史数据 DataFrame
        """
        # 时间周期映射到 kType 参数
        ktype_map = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '4h': 240, '1d': 1440, '1w': 10080
        }
        ktype = ktype_map.get(timeframe, 1440)

        params = {
            'code': symbol,
            'kType': ktype,
            'start': int(start_date.timestamp() * 1000),  # 毫秒时间戳
            'end': int(end_date.timestamp() * 1000),      # 毫秒时间戳
            'region': region
        }

        data = self._request(self.endpoints['history'], params)

        # 解析历史数据（根据 iTick API 实际返回格式）
        if 'data' in data and isinstance(data['data'], list):
            history_list = []

            for item in data['data']:
                ts = item.get('t', 0)
                if ts > 1e12:  # 毫秒时间戳
                    ts = ts / 1000
                history_list.append({
                    'timestamp': datetime.fromtimestamp(ts),
                    'open': item.get('o'),
                    'high': item.get('h'),
                    'low': item.get('l'),
                    'close': item.get('c'),
                    'volume': item.get('v', 0)
                })

            df = pd.DataFrame(history_list)
            if not df.empty:
                df.set_index('timestamp', inplace=True)
                df.sort_index(inplace=True)

            return df

        return pd.DataFrame()

    def save_raw_data(self, df: pd.DataFrame, symbol: str, timeframe: str):
        """
        保存原始数据到文件

        Args:
            df: 数据 DataFrame
            symbol: 交易品种代码
            timeframe: 时间周期
        """
        output_dir = Path('data/raw')
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{symbol}_{timeframe}_{timestamp}.csv"
        filepath = output_dir / filename

        df.to_csv(filepath)
        return filepath

    def load_raw_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """
        加载最新的原始数据

        Args:
            symbol: 交易品种代码
            timeframe: 时间周期

        Returns:
            数据 DataFrame
        """
        output_dir = Path('data/raw')

        # 查找匹配的最新文件
        pattern = f"{symbol}_{timeframe}_*.csv"
        files = list(output_dir.glob(pattern))

        if not files:
            return None

        # 按修改时间排序，获取最新文件
        latest_file = max(files, key=lambda f: f.stat().st_mtime)

        df = pd.read_csv(latest_file, index_col='timestamp', parse_dates=True)
        return df
