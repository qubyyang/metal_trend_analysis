"""
新浪财经数据源提供器（国内直连，贵金属现货）

背景：Stooq 已启用 JS 反爬挑战、Yahoo Finance 对部分地区返回 403，
两者在中国大陆网络环境下均不可靠。新浪财经的全球期货日线接口
无需鉴权且国内直连稳定，作为主力数据源使用。

接口特点：
- 返回 JSONP（``x([...])``），需剥离回调包装后解析
- 响应体前缀含一段防盗链 script 注释，必须先行剥除
- 需携带 Referer 头，否则可能被拒绝
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import pandas as pd
import requests

from ..utils.exceptions import DataFetchError, NetworkError
from .base_provider import BaseDataProvider

# 通用代码 -> 新浪全球期货代码
SYMBOL_MAP = {
    "XAUUSD": "XAU",  # 伦敦金（现货黄金）
    "XAGUSD": "XAG",  # 伦敦银（现货白银）
}

# 剥离 JSONP 回调包装：x([...]) / var x = [...]
_JSONP_PATTERN = re.compile(r"^[^(\[]*\(|\);?\s*$")


class SinaProvider(BaseDataProvider):
    """新浪财经贵金属日线数据源"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_url = self.config.get(
            "sina_base_url",
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/x/"
            "GlobalFuturesService.getGlobalFuturesDailyKLine",
        )

    @property
    def name(self) -> str:
        return "sina"

    def supports(self, symbol: str) -> bool:
        """仅支持已映射的贵金属品种"""
        return bool(symbol) and symbol.upper() in SYMBOL_MAP

    def _resolve_symbol(self, symbol: str) -> str:
        resolved = SYMBOL_MAP.get(symbol.upper())
        if not resolved:
            raise DataFetchError(f"[sina] 不支持的品种: {symbol}")
        return resolved

    @staticmethod
    def _strip_jsonp(text: str) -> str:
        """剥离防盗链注释与 JSONP 回调包装，返回纯 JSON 字符串"""
        cleaned = text.strip()

        # 移除形如 /*<script>location.href='//sina.com';</script>*/ 的前缀注释
        if cleaned.startswith("/*"):
            end = cleaned.find("*/")
            if end != -1:
                cleaned = cleaned[end + 2:].strip()

        # 定位数组主体，避免正则误伤内容
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise DataFetchError("[sina] 响应中未找到合法的 JSON 数组")

        return cleaned[start:end + 1]

    def fetch_daily(self, symbol: str) -> pd.DataFrame:
        sina_symbol = self._resolve_symbol(symbol)

        try:
            response = requests.get(
                self.base_url,
                params={"symbol": sina_symbol, "_": "1"},
                timeout=self.timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    ),
                    "Referer": "https://finance.sina.com.cn",
                },
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise NetworkError(f"[sina] 请求 {symbol} 失败: {e}")

        try:
            records = json.loads(self._strip_jsonp(response.text))
        except (ValueError, DataFetchError) as e:
            raise DataFetchError(f"[sina] {symbol} 响应解析失败: {e}")

        if not isinstance(records, list) or not records:
            raise DataFetchError(f"[sina] {symbol} 无数据返回")

        df = pd.DataFrame(records)

        required = {"date", "open", "high", "low", "close"}
        if not required.issubset(df.columns):
            raise DataFetchError(
                f"[sina] {symbol} 数据字段缺失: {sorted(required - set(df.columns))}"
            )

        df.index = pd.to_datetime(df["date"], errors="coerce")
        df.index.name = "timestamp"
        df = df[df.index.notna()]

        if df.empty:
            raise DataFetchError(f"[sina] {symbol} 日期解析后无有效数据")

        columns = ["open", "high", "low", "close"]
        if "volume" in df.columns:
            columns.append("volume")

        return df[columns]
