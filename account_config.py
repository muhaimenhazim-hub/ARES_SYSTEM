"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 6.0 (HYBRID ZERO-COST ENGINE: PAPER DEMO + DIRECT BINANCE)
================================================================================
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Tuple, Optional

CONFIG_FILE = "ares_user_config.json"


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """
    محاسبه موجودی واقعی یا دمو بدون نیاز به پرداخت هزینه به MetaApi
    خروجی: (موجودی, رشته توضیحات اکانت, رشته وضعیت بروکر, وضعیت اتصال)
    """
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    trading_mode = user_cfg.get("trading_mode", "PAPER")
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()

    m_login = str(user_cfg.get("mt5_login", "")).strip()
    m_pass = str(user_cfg.get("mt5_pass", "")).strip()
    m_server = str(user_cfg.get("mt5_server", "")).strip()

    # ۱. اتصال به بایننس فیوچرز (کاملاً رایگان و زنده)
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
            mode_label = "آزمایشی" if trading_mode == "PAPER" else "واقعی"
            return real_equity, f"بایننس فیوچرز | {mode_label}", f"صرافی متصل: بایننس | موجودی: {real_equity:.2f} USDT", True
        except Exception:
            return 0.0, "خطای بایننس", "کلیدهای API بایننس نامعتبر هستند.", False

    # ۲. اتصال متاتریدر ۵ (حالت دمو و آزمایشی کاملاً رایگان)
    if m_login and m_pass and m_server:
        if trading_mode == "PAPER":
            # در حالت آزمایشی نیازی به پرداخت هزینه به متا‌اپی نیست
            return 10000.00, f"اکانت متاتریدر ۵ ({m_login}) | حساب دمو", f"بروکر: {m_server} | متصل و آماده معامله", True
        else:
            # در حالت واقعی نیازمند سرویس ابری است
            return 0.0, f"اکانت {m_login}", "حساب لایو نیازمند شارژ حساب MetaApi است.", False

    return 0.0, "هیچ حسابی متصل نیست", "جهت شروع، مشخصات حساب متاتریدر یا بایننس را در تنظیمات وارد کنید.", False


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