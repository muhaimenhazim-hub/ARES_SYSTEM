"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 1: UNIFIED MULTI-MARKET DATA CONNECTOR (Crypto & Forex & Indices)
VERSION: 2.1 (AUTO-BROKER SUFFIX RESOLVER)
================================================================================
ماموریت ماژول:
اتصال خودکار به بایننس فیوچرز و متاتریدر ۵ با قابلیت تشخیص خودکار پسوندهای بروکر (مانند .)
================================================================================
"""

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
    """کانکتور رسمی بازار فارکس و شاخص‌ها برای اتصال به تمام بروکرها"""

    TIMEFRAME_MAP = {
        "1h": 16385,   # mt5.TIMEFRAME_H1
        "15m": 15,     # mt5.TIMEFRAME_M15
        "5m": 5,       # mt5.TIMEFRAME_M5
    }

    def __init__(self):
        self.connected = False
        if not MT5_AVAILABLE:
            print("⚠️ کتابخانه MetaTrader5 نصب نشده است.")
            return

        if mt5.initialize():
            self.connected = True
            account_info = mt5.account_info()
            broker_name = account_info.company if account_info else "بروکر جاری"
            print(f"🔌 اتصال موفقیت‌آمیز به متاتریدر ۵ برقرار شد | بروکر: {broker_name} | سرور: {account_info.server}")
        else:
            print("⚠️ امکان اتصال به متاتریدر ۵ وجود ندارد.")

    def resolve_broker_symbol(self, standard_symbol: str) -> Optional[str]:
        """پیدا کردن هوشمند نام نماد با توجه به پسوندهای بروکر (مثلاً نقطه یا m)"""
        # لیست تمام نمادهای موجود در بروکر
        all_symbols = mt5.symbols_get()
        if not all_symbols:
            return None

        clean_target = standard_symbol.upper().replace(" ", "")

        # ۱. ابتدا بررسی تطابق دقیق یا پسوندهای رایج
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

        # ۲. جستجوی زیررشته‌ای
        for s_name in available_names:
            if clean_target in s_name:
                mt5.symbol_select(s_name, True)
                return s_name

        return None

    def fetch_ohlcv(self, standard_symbol: str, timeframe: str = "15m", limit: int = 100) -> Optional[pd.DataFrame]:
        if not self.connected:
            return None

        broker_symbol = self.resolve_broker_symbol(standard_symbol)
        if not broker_symbol:
            print(f"⚠️ نماد {standard_symbol} در مارکت واچ بروکر شما یافت نشد.")
            return None

        tf_val = self.TIMEFRAME_MAP.get(timeframe, 15)
        rates = mt5.copy_rates_from_pos(broker_symbol, tf_val, 0, limit)

        if rates is None or len(rates) < 15:
            return None

        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s")
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(np.float64)

        return df[["timestamp", "open", "high", "low", "close", "volume"]]


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

    # ۲. تست زنده دریافت طلا از متاتریدر ۵
    print("\n--- آزمایش ۲: دریافت دیتای زنده فارکس (طلا) از متاتریدر ۵ ---")
    if data_hub.mt5.connected:
        gold_data = data_hub.get_live_multitimeframe_bundle("XAUUSD")
        if gold_data:
            print(f"✅ فارکس فعال است: قیمت زنده هر انس طلا = {gold_data['current_price']} دلار")
        else:
            # تست با جفت‌ارز یورو/دلار
            eur_data = data_hub.get_live_multitimeframe_bundle("EURUSD")
            if eur_data:
                print(f"✅ فارکس فعال است: قیمت زنده EURUSD = {eur_data['current_price']}")
    print("=" * 75)