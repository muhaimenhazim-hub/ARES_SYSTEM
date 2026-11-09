"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 7.0 (MQL5 LIVE BRIDGE ENGINE)
================================================================================
"""

import json
import os
from typing import Dict, Any, Tuple

CONFIG_FILE = "ares_user_config.json"

# کش وضعیت حساب‌های زنده متصل از طریق اکسپرت متاتریدر
BRIDGE_LIVE_DATA: Dict[str, Dict[str, Any]] = {}


def update_bridge_data(identifier: str, data: Dict[str, Any]):
    """بروزرسانی زنده موجودی و معاملات توسط اکسپرت متاتریدر"""
    BRIDGE_LIVE_DATA[identifier.strip().lower()] = data


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """
    خواندن موجودی ۱۰۰٪ واقعی از متاتریدر ۵ یا بایننس بدون دیتای فرضی
    """
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    # ۱. بررسی اتصال زنده از طریق اکسپرت متاتریدر
    # اگر کاربر با موبایل یا ایمیل ثبت‌نام کرده باشد، از همان برای انطباق استفاده می‌شود
    user_id = str(user_cfg.get("user_id", "")).strip().lower()
    m_login = str(user_cfg.get("mt5_login", "")).strip()

    # جستجو در دیتای ارسال‌شده توسط اکسپرت متاتریدر
    for key, bridge in BRIDGE_LIVE_DATA.items():
        if key in user_id or str(bridge.get("login")) == m_login:
            eq = float(bridge.get("equity", 0.0))
            company = bridge.get("broker", "بروکر متصل")
            server = bridge.get("server", "سرور متاتریدر")
            login_num = bridge.get("login", "")
            return eq, f"اکانت متاتریدر {login_num} (زنده)", f"بروکر: {company} | سرور: {server} | متصل و آنلاین", True

    # ۲. بررسی بایننس فیوچرز
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()
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
            return real_equity, "بایننس فیوچرز (زنده)", f"صرافی متصل: بایننس | موجودی: {real_equity:.2f} USDT", True
        except Exception:
            return 0.0, "خطای بایننس", "کلیدهای API بایننس نامعتبر هستند.", False

    return 0.0, "در انتظار اتصال اکسپرت متاتریدر", "اکسپرت AresBridgeEA را در متاتریدر فعال کنید تا متصل شود.", False


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)


def fetch_live_account_balance() -> Tuple[float, str, str, bool]:
    cfg = load_config()
    return fetch_user_live_balance(cfg)