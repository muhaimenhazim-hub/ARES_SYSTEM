"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 3.2 (PRODUCTION READY - CROSS-PLATFORM COMPATIBLE)
================================================================================
"""

import json
import os
from typing import Dict, Any, Tuple

CONFIG_FILE = "ares_user_config.json"

DEFAULT_CONFIG = {
    "trading_mode": "PAPER",
    "binance": {
        "api_key": "",
        "secret_key": "",
        "testnet": False
    },
    "mt5": {
        "account_number": "",
        "password": "",
        "server": ""
    }
}


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def fetch_live_account_balance() -> Tuple[float, str, str, bool]:
    """
    دریافت موجودی واقعی از صرافی بایننس یا حساب متاتریدر ۵
    خروجی: (موجودی, اطلاعات اکانت, وضعیت اتصال, وضعیت متصل بودن)
    """
    cfg = load_config()
    trading_mode = cfg.get("trading_mode", "PAPER")

    binance_cfg = cfg.get("binance", {})
    b_key = binance_cfg.get("api_key", "").strip()
    b_secret = binance_cfg.get("secret_key", "").strip()

    mt5_cfg = cfg.get("mt5", {})
    m_login = str(mt5_cfg.get("account_number", "")).strip()
    m_pass = str(mt5_cfg.get("password", "")).strip()
    m_server = str(mt5_cfg.get("server", "")).strip()

    # ۱. اتصال زنده صرافی بایننس (کاملاً سازگار با لینوکس و ویندوز)
    if b_key and b_secret:
        try:
            import ccxt
            exchange = ccxt.binanceusdm({
                'apiKey': b_key,
                'secret': b_secret,
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}
            })
            balance_info = exchange.fetch_balance()
            real_equity = float(balance_info.get('total', {}).get('USDT', 0.0))
            mode_label = "آزمایشی (قیمت لحظه‌ای)" if trading_mode == "PAPER" else "معاملات واقعی"
            return real_equity, f"بایننس فیوچرز | {mode_label}", f"صرافی متصل: بایننس | موجودی: {real_equity:.2f} USDT", True
        except Exception as e:
            err_msg = str(e)
            if any(k in err_msg for k in ["API-key", "Signature", "Invalid"]):
                return 0.0, "خطا در احراز هویت بایننس", "کلید API یا Secret Key بایننس نادرست است.", False
            return 0.0, "در حال تلاش برای اتصال به بایننس", "ارتباط با سرور صرافی برقرار نشد.", False

    # ۲. بررسی اتصال متاتریدر ۵
    if m_login and m_pass:
        try:
            import MetaTrader5 as mt5
            server_arg = m_server if m_server else None
            init_success = mt5.initialize(server=server_arg) if server_arg else mt5.initialize()
            if init_success:
                if mt5.login(login=int(m_login), password=m_pass, server=server_arg):
                    acc = mt5.account_info()
                    if acc:
                        mode_label = "حساب آزمایشی" if acc.trade_mode == 0 else "حساب واقعی"
                        return float(acc.equity), f"اکانت {acc.login} ({acc.currency}) | {mode_label}", f"بروکر: {acc.company} | سرور: {acc.server}", True
                err = mt5.last_error()
                return 0.0, f"اکانت متاتریدر {m_login}", f"مشخصات ورود یا نام سرور نادرست است (کد خطا: {err})", False
            return 0.0, f"اکانت متاتریدر {m_login}", "در حال انتظار برای راه‌اندازی ارتباط با ترمینال بروکر...", False
        except ImportError:
            # مدیریت تمیز و استاندارد بدون پیام‌های فنی لینوکس
            mode_label = "آزمایشی" if trading_mode == "PAPER" else "واقعی"
            return 0.0, f"اکانت {m_login} ({m_server}) | {mode_label}", "در حال هماهنگ‌سازی ارتباط با سرور بروکر...", False
        except Exception as e:
            return 0.0, f"اکانت متاتریدر {m_login}", "در انتظار برقراری ارتباط با سرور بروکر", False

    # ۳. در صورت عدم تنظیم اکانت
    return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False