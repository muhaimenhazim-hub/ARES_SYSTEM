"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 1: UNIFIED MULTI-MARKET DATA CONNECTOR (Crypto & Forex & Indices)
VERSION: 14.3 (2s LIVE MT5 QUOTES FOR ALL SYMBOLS + 1m XAUUSD + H4/D1 SUPPORT)
================================================================================
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import ccxt
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_CANDLES_FILE = os.path.join(BASE_DIR, "ares_live_candles.json")
BRIDGE_CACHE_FILE = os.path.join(BASE_DIR, "ares_bridge_cache.json")
LIVE_CANDLES_MAX_AGE_SECONDS = 90.0
LIVE_QUOTE_MAX_AGE_SECONDS = 15.0


class BinanceFuturesConnector:
    """کانکتور رسمی بازار کریپتو فیوچرز بایننس"""

    CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "XRPUSDT", "1000PEPEUSDT"]

    def __init__(self):
        self.exchange = ccxt.binance({
            "options": {"defaultType": "future"},
            "enableRateLimit": True,
            "timeout": 7000,
        })

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        min_len: int = 15,
    ) -> Optional[pd.DataFrame]:
        base = symbol.replace("USDT", "")
        formatted_symbol = f"{base}/USDT:USDT"
        try:
            raw = self.exchange.fetch_ohlcv(symbol=formatted_symbol, timeframe=timeframe, limit=limit)
            if not raw or len(raw) < min_len:
                return None
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(np.float64)
            return df
        except Exception:
            return None


class MT5ForexConnector:
    """کانکتور زنده و پرسرعت انس طلا، فارکس و شاخص‌ها بر بستر کلود جهانی"""

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

    def _fetch_cloud_ohlcv(
        self,
        standard_symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        min_len: int = 15,
    ) -> Optional[pd.DataFrame]:
        clean_sym = standard_symbol.upper().replace(" ", "").replace("/", "").replace(".", "")
        cloud_sym = self.SYMBOL_MAP.get(standard_symbol, self.SYMBOL_MAP.get(clean_sym, f"{clean_sym}=X"))

        is_4h_resample = (timeframe == "4h")
        api_interval = "1h" if is_4h_resample else timeframe
        range_map = {"1m": "2d", "5m": "5d", "15m": "5d", "1h": "1mo", "4h": "1mo", "1d": "3mo"}
        fetch_range = range_map.get(timeframe, "5d")

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cloud_sym}?interval={api_interval}&range={fetch_range}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
                payload = json.loads(response.read().decode())
                if not payload.get("chart", {}).get("result"):
                    return self._fetch_gold_backup(timeframe, limit, min_len=min_len) if ("XAU" in clean_sym or "GOLD" in clean_sym) else None

                result = payload["chart"]["result"][0]
                timestamps = result.get("timestamp", [])
                quote = result.get("indicators", {}).get("quote", [{}])[0]

                if not timestamps or not quote.get("close"):
                    return None

                df = pd.DataFrame({
                    "timestamp": pd.to_datetime(timestamps, unit="s"),
                    "open": quote.get("open", [0] * len(timestamps)),
                    "high": quote.get("high", [0] * len(timestamps)),
                    "low": quote.get("low", [0] * len(timestamps)),
                    "close": quote.get("close", [0] * len(timestamps)),
                    "volume": quote.get("volume", [0] * len(timestamps)),
                }).dropna()

                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(np.float64)

                if is_4h_resample:
                    df = (
                        df.set_index("timestamp")
                        .resample("4h")
                        .agg({
                            "open": "first",
                            "high": "max",
                            "low": "min",
                            "close": "last",
                            "volume": "sum",
                        })
                        .dropna()
                        .reset_index()
                    )

                if len(df) < min_len:
                    return None

                return df.tail(limit)[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
        except Exception:
            if "XAU" in clean_sym or "GOLD" in clean_sym:
                return self._fetch_gold_backup(timeframe, limit, min_len=min_len)
            return None

    def _fetch_gold_backup(
        self,
        timeframe: str = "15m",
        limit: int = 100,
        min_len: int = 15,
    ) -> Optional[pd.DataFrame]:
        try:
            ex = ccxt.binance({"options": {"defaultType": "future"}, "enableRateLimit": True, "timeout": 5000})
            raw = ex.fetch_ohlcv("PAXG/USDT:USDT", timeframe=timeframe, limit=limit)
            if not raw or len(raw) < min_len:
                return None
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(np.float64)
            return df
        except Exception:
            return None

    def fetch_ohlcv(
        self,
        standard_symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        min_len: int = 15,
    ) -> Optional[pd.DataFrame]:
        return self._fetch_cloud_ohlcv(standard_symbol, timeframe, limit, min_len=min_len)


class AresUnifiedDataService:
    """هاب مرکزی داده‌های زنده ARES با اولویت قیمت ۲ ثانیه‌ای و کندل‌های لحظه‌ای متاتریدر (MT5_LIVE)"""

    def __init__(self, cache_ttl_seconds: float = 1.5):
        self.binance = BinanceFuturesConnector()
        self.mt5 = MT5ForexConnector()
        self.cache_ttl = cache_ttl_seconds
        self._bundle_cache: Dict[str, Tuple[float, Dict]] = {}

    @staticmethod
    def _rates_to_dataframe(rows: object, min_len: int = 15) -> Optional[pd.DataFrame]:
        if not isinstance(rows, list) or len(rows) < min_len:
            return None
        try:
            df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"]).dropna()
            if len(df) < min_len:
                return None
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(np.float64)
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df
        except Exception:
            return None

    @staticmethod
    def _get_live_mt5_quote_price(symbol: str, preferred_login: str = "") -> Optional[float]:
        """خواندن قیمت لحظه‌ای ۲ ثانیه‌ای (Bid) از کش همگام‌سازی متاتریدر برای تمام نمادها"""
        if not os.path.exists(BRIDGE_CACHE_FILE):
            return None
        try:
            with open(BRIDGE_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if not isinstance(cache, dict):
                return None

            now_ts = time.time()
            best_ts = 0.0
            best_bid: Optional[float] = None
            pref = str(preferred_login or "").strip()

            for snap in cache.values():
                if not isinstance(snap, dict):
                    continue
                ts = float(snap.get("last_sync_ts", 0.0) or 0.0)
                if ts <= 0.0 or (now_ts - ts) > LIVE_QUOTE_MAX_AGE_SECONDS:
                    continue
                quotes = snap.get("live_quotes")
                if not isinstance(quotes, dict):
                    continue
                q = quotes.get(symbol)
                if not isinstance(q, dict):
                    continue
                bid = float(q.get("bid", 0.0) or 0.0)
                if bid <= 0.0:
                    continue

                snap_login = str(snap.get("login", "")).strip()
                if pref and snap_login == pref:
                    return bid
                if ts > best_ts:
                    best_ts = ts
                    best_bid = bid

            return best_bid
        except Exception:
            return None

    def _load_mt5_live_bundle(self, symbol: str) -> Optional[Dict]:
        if not os.path.exists(LIVE_CANDLES_FILE):
            return None
        try:
            with open(LIVE_CANDLES_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return None
            symbols_map = payload.get("symbols")
            if not isinstance(symbols_map, dict):
                return None
            sym_entry = symbols_map.get(symbol)
            if not isinstance(sym_entry, dict):
                return None

            updated_ts = float(sym_entry.get("updated_ts", 0.0) or 0.0)
            if updated_ts <= 0.0 or (time.time() - updated_ts) > LIVE_CANDLES_MAX_AGE_SECONDS:
                return None

            df_htf = self._rates_to_dataframe(sym_entry.get("1h"), min_len=10)
            df_mtf = self._rates_to_dataframe(sym_entry.get("15m"), min_len=15)
            df_ltf = self._rates_to_dataframe(sym_entry.get("5m"), min_len=15)
            if df_htf is None or df_mtf is None or df_ltf is None:
                return None

            df_h4 = self._rates_to_dataframe(sym_entry.get("4h"), min_len=8)
            df_d1 = self._rates_to_dataframe(sym_entry.get("1d"), min_len=4)
            df_1m = self._rates_to_dataframe(sym_entry.get("1m"), min_len=20)

            preferred_login = str(sym_entry.get("login", "")).strip()
            live_bid = self._get_live_mt5_quote_price(symbol, preferred_login=preferred_login)
            current_price = (
                live_bid
                if live_bid is not None
                else (float(df_1m.iloc[-1]["close"]) if df_1m is not None else float(df_ltf.iloc[-1]["close"]))
            )
            if current_price <= 0.0:
                return None

            source_label = str(sym_entry.get("source", "")).strip() or "MT5_LIVE"
            return {
                "symbol": symbol,
                "market_type": "FOREX_OR_INDICES",
                "current_price": current_price,
                "df_htf": df_htf,
                "df_mtf": df_mtf,
                "df_ltf": df_ltf,
                "df_h4": df_h4,
                "df_d1": df_d1,
                "df_1m": df_1m,
                "source": source_label,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return None

    def get_live_multitimeframe_bundle(self, symbol: str) -> Optional[Dict]:
        now = time.time()
        if symbol in self._bundle_cache:
            ts, cached_bundle = self._bundle_cache[symbol]
            if now - ts < self.cache_ttl:
                return cached_bundle

        if symbol in self.binance.CRYPTO_SYMBOLS:
            market_type = "CRYPTO_FUTURES"
            df_htf = self.binance.fetch_ohlcv(symbol, timeframe="1h", limit=50)
            df_mtf = self.binance.fetch_ohlcv(symbol, timeframe="15m", limit=60)
            df_ltf = self.binance.fetch_ohlcv(symbol, timeframe="5m", limit=60)
            if df_htf is None or df_mtf is None or df_ltf is None:
                return None
            df_h4 = self.binance.fetch_ohlcv(symbol, timeframe="4h", limit=30, min_len=8)
            df_d1 = self.binance.fetch_ohlcv(symbol, timeframe="1d", limit=20, min_len=4)
            current_price = float(df_ltf.iloc[-1]["close"])
            bundle = {
                "symbol": symbol,
                "market_type": market_type,
                "current_price": current_price,
                "df_htf": df_htf,
                "df_mtf": df_mtf,
                "df_ltf": df_ltf,
                "df_h4": df_h4,
                "df_d1": df_d1,
                "source": "BINANCE_FUTURES",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._bundle_cache[symbol] = (now, bundle)
            return bundle

        # اولویت ۱: کندل‌های لحظه‌ای و بدون تاخیر مستقیم از متاتریدر ۵ سرور
        live_bundle = self._load_mt5_live_bundle(symbol)
        if live_bundle is not None:
            self._bundle_cache[symbol] = (now, live_bundle)
            return live_bundle

        # اولویت ۲ (پشتیبان): دریافت از یاهو فایننس در صورت نبود تیک زنده متاتریدر
        df_htf = self.mt5.fetch_ohlcv(symbol, timeframe="1h", limit=50)
        df_mtf = self.mt5.fetch_ohlcv(symbol, timeframe="15m", limit=60)
        df_ltf = self.mt5.fetch_ohlcv(symbol, timeframe="5m", limit=60)

        if df_htf is None or df_mtf is None or df_ltf is None:
            return None

        df_h4 = self.mt5.fetch_ohlcv(symbol, timeframe="4h", limit=30, min_len=8)
        df_d1 = self.mt5.fetch_ohlcv(symbol, timeframe="1d", limit=20, min_len=4)
        df_1m = self.mt5.fetch_ohlcv(symbol, timeframe="1m", limit=65, min_len=20) if symbol == "XAUUSD" else None
        live_bid = self._get_live_mt5_quote_price(symbol)
        current_price = (
            live_bid
            if live_bid is not None
            else (float(df_1m.iloc[-1]["close"]) if df_1m is not None else float(df_ltf.iloc[-1]["close"]))
        )

        bundle = {
            "symbol": symbol,
            "market_type": "FOREX_OR_INDICES",
            "current_price": current_price,
            "df_htf": df_htf,
            "df_mtf": df_mtf,
            "df_ltf": df_ltf,
            "df_h4": df_h4,
            "df_d1": df_d1,
            "df_1m": df_1m,
            "source": "YAHOO_BACKUP",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._bundle_cache[symbol] = (now, bundle)
        return bundle