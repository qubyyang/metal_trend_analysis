"""
新浪外汇数据源提供器（美元指数等宏观参照品种）

与 ``SinaProvider``（全球期货 JSONP 数组接口）不同，本 provider 走的是
新浪**外汇**日线接口，两者在响应格式上完全不兼容，因此独立实现：

- 期货接口返回 JSON 数组：``x([{"date":...,"open":...}, ...])``
- 外汇接口返回**管道分隔的 CSV 字符串**：
  ``x("1985-11-08,129.2200,128.9100,129.6600,129.1300,|...")``

字段顺序为 ``date, open, low, high, close``（注意 low 在 high 之前）。
该顺序于 2026-09-04 经两步实测确认：

1. 对最近 2000 根 K 线穷举 4 个价格字段的全部排列，检验
   ``low <= min(open, close) <= max(open, close) <= high``；
   仅 ``(1,2,3,4)`` 与 ``(4,2,3,1)`` 两种排列零违例（open/close 对调
   在数学上同样自洽，无法据此区分）。
2. 以「昨收 ≈ 今开」的连续性消歧：方案 A（idx1=open, idx4=close）
   平均跳空 0.0218，方案 B（对调）为 0.4496，相差约 20 倍，
   故确定为方案 A。最新收盘 99.15 亦与实时行情接口 99.1550 吻合。

另注：全球期货接口下的美元指数代码 ``DX`` 已停更于 2019-05，
``DXY`` / ``USDX`` / ``UDI`` 均返回空，只有本接口的 ``DINIW`` 仍在更新。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError, NetworkError
from .base_provider import BaseDataProvider

# 通用代码 -> 新浪外汇代码
SYMBOL_MAP = {
    "DXY": "DINIW",     # 美元指数
    "USDIDX": "DINIW",  # 别名
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}


class SinaForexProvider(BaseDataProvider):
    """新浪外汇日线数据源（美元指数）"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get(
            "sina_forex_base_url",
            "https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/x/"
            "NewForexService.getDayKLine",
        )

    @property
    def name(self) -> str:
        return "sina_forex"

    def supports(self, symbol: str) -> bool:
        return bool(symbol) and symbol.upper() in SYMBOL_MAP

    def _resolve_symbol(self, symbol: str) -> str:
        resolved = SYMBOL_MAP.get(symbol.upper())
        if not resolved:
            raise DataFetchError(f"[sina_forex] 不支持的品种: {symbol}")
        return resolved

    @staticmethod
    def _extract_payload(text: str) -> str:
        """从 JSONP 包装中取出管道分隔的 CSV 主体"""
        cleaned = text.strip()

        # 剥除防盗链注释前缀 /*<script>...</script>*/
        if cleaned.startswith("/*"):
            end = cleaned.find("*/")
            if end != -1:
                cleaned = cleaned[end + 2:].strip()

        # 数据为字符串形式：x("...")；空数据为对象形式：x({"msg":"data is empty"})
        start = cleaned.find('x("')
        end = cleaned.rfind('")')
        if start == -1 or end == -1 or end <= start:
            raise DataFetchError("[sina_forex] 响应中未找到日线数据主体")

        payload = cleaned[start + 3:end]
        if not payload.strip():
            raise DataFetchError("[sina_forex] 日线数据主体为空")

        return payload

    def fetch_daily(self, symbol: str) -> pd.DataFrame:
        sina_symbol = self._resolve_symbol(symbol)

        try:
            response = requests.get(
                self.base_url,
                params={"symbol": sina_symbol},
                timeout=self.timeout,
                headers=_HEADERS,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise NetworkError(f"[sina_forex] 请求 {symbol} 失败: {e}")

        payload = self._extract_payload(response.text)

        records = []
        for chunk in payload.split("|"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split(",")
            if len(parts) < 5:
                continue
            # date, open, low, high, close —— 注意 low 先于 high
            records.append({
                "date": parts[0],
                "open": parts[1],
                "low": parts[2],
                "high": parts[3],
                "close": parts[4],
            })

        if not records:
            raise DataFetchError(f"[sina_forex] {symbol} 无有效日线记录")

        df = pd.DataFrame(records)
        df.index = pd.to_datetime(df["date"], errors="coerce")
        df.index.name = "timestamp"
        df = df[df.index.notna()]

        if df.empty:
            raise DataFetchError(f"[sina_forex] {symbol} 日期解析后无有效数据")

        # 提前数值化：外汇接口返回的是字符串，若留到 _standardize 才转换，
        # 期间任何基于大小的比较都会退化为字符串比较（"99.5" < "9.9" 为真），
        # 属于极易误判的隐性缺陷。
        result = df[["open", "high", "low", "close"]].apply(
            pd.to_numeric, errors="coerce"
        )
        result = result.dropna(subset=["open", "high", "low", "close"])

        if result.empty:
            raise DataFetchError(f"[sina_forex] {symbol} 数值化后无有效数据")

        return result
