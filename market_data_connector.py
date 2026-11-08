"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 1: UNIFIED MULTI-MARKET DATA CONNECTOR (Crypto & Forex & Indices)
VERSION: 3.0 (HYBRID NATIVE MT5 & CLOUD FOREX/GOLD ENGINE FOR LINUX)
================================================================================
ماموریت ماژول:
اتصال خودکار به بایننس فیوچرز و متاتریدر ۵ با قابلیت سوئیچ خودکار به دیتای ابری
در سرورهای لینوکس جهت فعال ماندن ۱۰۰٪ دیتای زنده طلا و جفت‌ارزها.
================================================================================
"""

import json
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional
import ccxt
import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False


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
    """کانکتور رسمی بازار فارکس و طلا با پشتیبانی هم‌زمان از متاتریدر ویندوز و سرور ابری لینوکس"""

    TIMEFRAME_MAP = {
        "1h": 16385,   # mt5.TIMEFRAME_H1
        "15m": 15,     # mt5.TIMEFRAME_M15
        "5m": 5,       # mt5.TIMEFRAME_M5
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
        "NASDAQ": "NQ=F",
        "USTEC": "NQ=F",
        "NAS100": "NQ=F",
        "US100": "NQ=F",
        "SP500": "ES=F",
        "US500": "ES=F",
    }

    def __init__(self):
        self.connected = False
        self.mode = "MT5"

        # ۱. تلاش برای اتصال به نرم‌افزار بومی متاتریدر (در ویندوز)
        if MT5_AVAILABLE:
            try:
                if mt5.initialize():
                    self.connected = True
                    self.mode = "MT5_NATIVE"
                    account_info = mt5.account_info()
                    broker_name = account_info.company if account_info else "بروکر جاری"
                    print(f"🔌 اتصال به متاتریدر ۵ برقرار شد | بروکر: {broker_name} | سرور: {account_info.server}")
                    return
            except Exception:
                pass

        # ۲. در سرور ابری لینوکس: فعال‌سازی خودکار دیتای زنده جهانی فارکس و طلا
        self.connected = True
        self.mode = "CLOUD_FOREX"
        print("🌐 دیتای زنده بازار فارکس و انس طلا (XAUUSD) روی سرور ابری فعال شد.")

    def resolve_broker_symbol(self, standard_symbol: str) -> Optional[str]:
        """پیدا کردن هوشمند نام نماد با توجه به پسوندهای بروکر"""
        if self.mode != "MT5_NATIVE":
            return standard_symbol

        all_symbols = mt5.symbols_get()
        if not all_symbols:
            return None

        clean_target = standard_symbol.upper().replace(" ", "")

        search_candidates = [
            clean_target,
            f"{clean_target}.",
            f"{clean_target}m",
            f"{clean_target}.a",
        ]

        if "XAUUSD" in clean_target:
            search_candidates.extend(["GOLD", "GOLD.", "GOLDm", "XAUUSD.", "XAUUSD"])
        elif "NASDAQ" in clean_target:
            search_candidates.extend(["USTEC", "USTEC.", "NAS100", "NAS100.", "US100", "NDX"])
        elif "S&P" in clean_target:
            search_candidates.extend(["US500", "US500.", "SPX500", "SP500"])

        available_names = [s.name for s in all_symbols]

        for cand in search_candidates:
            if cand in available_names:
                mt5.symbol_select(cand, True)
                return cand

        for s_name in available_names:
            if clean_target in s_name:
                mt5.symbol_select(s_name, True)
                return s_name

        return None

    def _fetch_cloud_ohlcv(self, standard_symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """دریافت زنده و بدون وقفه کندل‌های طلا و فارکس بر روی سرور لینوکس"""
        clean_sym = standard_symbol.upper().replace(" ", "").replace("/", "").replace(".", "")
        cloud_sym = self.SYMBOL_MAP.get(clean_sym, f"{clean_sym}=X")

        range_map = {"5m": "5d", "15m": "5d", "1h": "1mo"}
        fetch_range = range_map.get(timeframe, "5d")

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{cloud_sym}?interval={timeframe}&range={fetch_range}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        try:
            with urllib.request.urlopen(req, timeout=6.0) as response:
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
            # پشتیبان فوری انس طلا در صورت بروز هرگونه قطعی
            if "XAU" in clean_sym or "GOLD" in clean_sym:
                return self._fetch_gold_backup(timeframe, limit)
            return None

    def _fetch_gold_backup(self, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        """پشتیبان زنده قیمت هر انس طلا بر بستر سرورهای PAXG"""
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
        if not self.connected:
            return None

        # اجرای حالت بومی در ویندوز
        if self.mode == "MT5_NATIVE" and MT5_AVAILABLE:
            broker_symbol = self.resolve_broker_symbol(standard_symbol)
            if broker_symbol:
                tf_val = self.TIMEFRAME_MAP.get(timeframe, 15)
                rates = mt5.copy_rates_from_pos(broker_symbol, tf_val, 0, limit)
                if rates is not None and len(rates) >= 15:
                    df = pd.DataFrame(rates)
                    df["timestamp"] = pd.to_datetime(df["time"], unit="s")
                    df.rename(columns={"tick_volume": "volume"}, inplace=True)
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = df[col].astype(np.float64)
                    return df[["timestamp", "open", "high", "low", "close", "volume"]]

        # اجرای حالت ابری برای سرور لینوکس
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


# ==============================================================================
# تست زنده دریافت هم‌زمان دیتای کریپتو و فارکس
# ==============================================================================
if __name__ == "__main__":
    print("=" * 75)
    print("ARES AI TRADING SYSTEM — UNIFIED DATA HUB (CRYPTO + FOREX)")
    print("=" * 75)

    data_hub = AresUnifiedDataService()

    # ۱. تست زنده دریافت بیت‌کوین از بایننس
    print("\n--- آزمایش ۱: دریافت دیتای زنده کریپتو از بایننس فیوچرز ---")
    crypto_data = data_hub.get_live_multitimeframe_bundle("BTCUSDT")
    if crypto_data:
        print(f"✅ کریپتو فعال است: قیمت زنده بیت‌کوین = {crypto_data['current_price']:,} دلار")

    # ۲. تست زنده دریافت طلا
    print("\n--- آزمایش ۲: دریافت دیتای زنده فارکس (طلا) ---")
    gold_data = data_hub.get_live_multitimeframe_bundle("XAUUSD")
    if gold_data:
        print(f"✅ انس طلا فعال است: قیمت زنده طلا = {gold_data['current_price']} دلار")
    else:
        eur_data = data_hub.get_live_multitimeframe_bundle("EURUSD")
        if eur_data:
            print(f"✅ جفت‌ارز یورو/دلار فعال است: قیمت = {eur_data['current_price']}")
    print("=" * 75)