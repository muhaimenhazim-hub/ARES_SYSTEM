"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 1: UNIFIED MULTI-MARKET DATA CONNECTOR (Crypto & Forex & Indices)
VERSION: 5.0 (HIGH-SPEED ZERO-DEPENDENCY CLOUD FEED & BINANCE FUTURES)
================================================================================
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Optional
import ccxt
import numpy as np
import pandas as pd


class BinanceFuturesConnector:
    """کانکتور رسمی بازار کریپتو فیوچرز بایننس"""

    CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "1000PEPEUSDT"]

    def __init__(self):
        self.exchange = ccxt.binance({
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
            "timeout": 7000,
        })

    def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        base = symbol.replace("USDT", "")
        formatted_symbol = f"{base}/USDT:USDT"
        try:
            raw = self.exchange.fetch_ohlcv(symbol=formatted_symbol, timeframe=timeframe, limit=limit)
            if not raw or len(raw) < 15:
                return None
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(np.float64)
            return df
        except Exception:
            return None


class MT5ForexConnector:
    """کانکتور زنده و پرسرعت انس طلا، فارکس و شاخص‌ها بر بستر کلود جهانی بدون نیاز به MetaApi"""

    TIMEFRAME_MAP = {
        "1h": "1h",
        "15m": "15m",
        "5m": "5m",
    }

    SYMBOL_MAP = {
        "XAUUSD": "GC=F",
        "GOLD": "GC=F",
        "EURUSD": "EURUSD=X",
        "GBPUSD": "GBPUSD=X",
        "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X",
        "USDCAD": "USDCAD=X",
        "USDCHF": "USDCHF=X",
        "NZDUSD": "NZDUSD=X",
        "NASDAQ 100": "NQ=F",
        "NASDAQ": "NQ=F",
        "USTEC": "NQ=F",
        "NAS100": "NQ=F",
        "US100": "NQ=F",
        "S&P 500": "ES=F",
        "SP500": "ES=F",
        "US500": "ES=F",
    }

    def __init__(self):
        print("🌐 دیتای زنده فارکس، انس طلا (XAUUSD) و شاخص‌ها بر بستر مستقل کلود فعال شد.")

    def _fetch_cloud_ohlcv(self, standard_symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """دریافت زنده و بدون وقفه کندل‌ها از سرورهای جهانی بدون تحریم و بدون افت سرعت"""
        clean_sym = standard_symbol.upper().replace(" ", "").replace("/", "").replace(".", "")
        cloud_sym = self.SYMBOL_MAP.get(standard_symbol, self.SYMBOL_MAP.get(clean_sym, f"{clean_sym}=X"))

        range_map = {"5m": "5d", "15m": "5d", "1h": "1mo"}
        fetch_range = range_map.get(timeframe, "5d")

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cloud_sym}?interval={timeframe}&range={fetch_range}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
                payload = json.loads(response.read().decode())
                if not payload.get("chart", {}).get("result"):
                    return self._fetch_gold_backup(timeframe, limit) if "XAU" in clean_sym or "GOLD" in clean_sym else None

                result = payload["chart"]["result"][0]
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                if not timestamps or not quote.get("close"):
                    return None

                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(timestamps, unit="s"),
                    "open": quote.get("open", [0]*len(timestamps)),
                    "high": quote.get("high", [0]*len(timestamps)),
                    "low": quote.get("low", [0]*len(timestamps)),
                    "close": quote.get("close", [0]*len(timestamps)),
                    "volume": quote.get("volume", [0]*len(timestamps)),
                }).dropna()

                if len(df) < 15:
                    return None

                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(np.float64)

                return df.tail(limit)[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception:
            if "XAU" in clean_sym or "GOLD" in clean_sym:
                return self._fetch_gold_backup(timeframe, limit)
            return None

    def _fetch_gold_backup(self, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """پشتیبان آنی قیمت انس طلا از استخر نقدینگی بایننس (PAXG) در صورت نوسانات شدید اینترنت"""
        try:
            ex = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True, "timeout": 5000})
            raw = ex.fetch_ohlcv("PAXG/USDT:USDT", timeframe=timeframe, limit=limit)
            if not raw or len(raw) < 15:
                return None
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(np.float64)
            return df
        except Exception:
            return None

    def fetch_ohlcv(self, standard_symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        return self._fetch_cloud_ohlcv(standard_symbol, timeframe, limit)


class AresUnifiedDataService:
    """هاب مرکزی داده‌های زنده ARES"""

    def __init__(self):
        self.binance = BinanceFuturesConnector()
        self.mt5 = MT5ForexConnector()

    def get_live_multitimeframe_bundle(self, symbol: str) -> Optional[Dict]:
        if symbol in self.binance.CRYPTO_SYMBOLS:
            market_type = "CRYPTO_FUTURES"
            connector = self.binance
        else:
            market_type = "FOREX_OR_INDICES"
            connector = self.mt5

        df_htf = connector.fetch_ohlcv(symbol, timeframe="1h", limit=50)
        df_mtf = connector.fetch_ohlcv(symbol, timeframe="15m", limit=60)
        df_ltf = connector.fetch_ohlcv(symbol, timeframe="5m", limit=60)

        if df_htf is None or df_mtf is None or df_ltf is None:
            return None

        current_price = float(df_ltf.iloc[-1]["close"])

        return {
            "symbol": symbol,
            "market_type": market_type,
            "current_price": current_price,
            "df_htf": df_htf,
            "df_mtf": df_mtf,
            "df_ltf": df_ltf,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }