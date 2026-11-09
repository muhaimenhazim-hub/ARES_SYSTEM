"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 1: UNIFIED MULTI-MARKET DATA CONNECTOR (Crypto & Forex & Indices)
VERSION: 4.0 (METAAPI CLOUD ENGINE + BINANCE FUTURES DIRECT FEED)
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

import account_config


class BinanceFuturesConnector:
    """کانکتور رسمی بازار کریپتو فیوچرز بایننس"""

    CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "1000PEPEUSDT"]

    def __init__(self):
        self.exchange = ccxt.binance({
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
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
        except Exception as e:
            print(f"❌ خطا در دریافت داده کریپتو {symbol}: {e}")
            return None


class MT5ForexConnector:
    """کانکتور رسمی بازار فارکس و طلا با MetaApi Cloud و شبکه بک‌آپ پرسرعت"""

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
        self.token = account_config.META_API_TOKEN
        self.connected = True
        print("🌐 دیتای زنده فارکس و انس طلا (XAUUSD) بر بستر سرورهای ابری فعال شد.")

    def _fetch_metaapi_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """تلاش اول: دریافت دیتا از حساب متصل در MetaApi"""
        if not account_config._METAAPI_ACCOUNT_CACHE:
            return None

        # گرفتن اولین اکانت ثبت شده در کش
        account_id = next(iter(account_config._METAAPI_ACCOUNT_CACHE.values()))
        clean_sym = symbol.replace(" ", "").upper()
        if "XAU" in clean_sym or "GOLD" in clean_sym:
            clean_sym = "XAUUSD"

        tf = self.TIMEFRAME_MAP.get(timeframe, "15m")
        url = f"https://mt-market-data-client-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts/{account_id}/historical-market-data/symbols/{clean_sym}/timeframes/{tf}/candles?limit={limit}"
        headers = {"auth-token": self.token, "User-Agent": "AresTradingSystem/4.0"}

        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                candles = json.loads(resp.read().decode())
                if candles and len(candles) >= 15:
                    df = pd.DataFrame(candles)
                    df["timestamp"] = pd.to_datetime(df["time"])
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in df.columns:
                            df[col] = df[col].astype(np.float64)
                    return df[["timestamp", "open", "high", "low", "close", "volume"]]
        except Exception:
            return None
        return None

    def _fetch_cloud_ohlcv(self, standard_symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """تلاش دوم: دریافت زنده و بدون وقفه کندل‌های طلا و فارکس بدون نیاز به پروکسی"""
        clean_sym = standard_symbol.upper().replace(" ", "").replace("/", "").replace(".", "")
        cloud_sym = self.SYMBOL_MAP.get(standard_symbol, self.SYMBOL_MAP.get(clean_sym, f"{clean_sym}=X"))

        range_map = {"5m": "5d", "15m": "5d", "1h": "1mo"}
        fetch_range = range_map.get(timeframe, "5d")

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cloud_sym}?interval={timeframe}&range={fetch_range}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        try:
            with urllib.request.urlopen(req, timeout=5.0) as response:
                payload = json.loads(response.read().decode())
                result = payload["chart"]["result"][0]
                timestamps = result["timestamp"]
                quote = result["indicators"]["quote"][0]

                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(timestamps, unit="s"),
                    "open": quote["open"],
                    "high": quote["high"],
                    "low": quote["low"],
                    "close": quote["close"],
                    "volume": quote.get("volume", [0] * len(timestamps)),
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
        """پشتیبان آنی قیمت انس طلا از استخر نقدینگی بایننس (PAXG)"""
        try:
            ex = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True})
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
        # ۱. ابتدا بررسی دریافت مستقیم از متاتریدر متصل کاربر
        df = self._fetch_metaapi_ohlcv(standard_symbol, timeframe, limit)
        if df is not None:
            return df

        # ۲. در غیر این صورت، دریافت از فید اختصاصی گلوبال ابری
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