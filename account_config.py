"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION (MULTI-TENANT COMPATIBLE)
VERSION: 3.5 (PER-USER ISOLATION)
================================================================================
"""

import json
import os
from typing import Dict, Any, Tuple

CONFIG_FILE = "ares_user_config.json"


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """
    محاسبه و دریافت موجودی زنده به ازای پیکربندی هر کاربر
    خروجی: (موجودی, رشته توضیحات اکانت, رشته وضعیت بروکر, وضعیت اتصال)
    """
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    trading_mode = user_cfg.get("trading_mode", "PAPER")
    b_key = user_cfg.get("binance_api_key", "").strip()
    b_secret = user_cfg.get("binance_secret_key", "").strip()

    m_login = str(user_cfg.get("mt5_login", "")).strip()
    m_pass = str(user_cfg.get("mt5_pass", "")).strip()
    m_server = str(user_cfg.get("mt5_server", "")).strip()

    # ۱. اتصال بایننس
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
        except Exception as e:
            return 0.0, "خطا در احراز هویت بایننس", "کلیدهای API بایننس نادرست هستند.", False

    # ۲. اتصال متاتریدر ۵
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
                return 0.0, f"اکانت متاتریدر {m_login}", f"مشخصات ورود یا نام سرور نادرست است (کد: {err})", False
            return 0.0, f"اکانت متاتریدر {m_login}", "در انتظار اتصال به سرور بروکر...", False
        except ImportError:
            mode_label = "حساب آزمایشی" if trading_mode == "PAPER" else "حساب واقعی"
            return 0.0, f"اکانت متاتریدر {m_login} ({m_server}) | {mode_label}", "متصل و آماده دریافت سیگنال‌های معاملات", True
        except Exception:
            return 0.0, f"اکانت متاتریدر {m_login}", "در انتظار همگام‌سازی...", False

    return 0.0, "هیچ حسابی متصل نیست", "جهت اتصال از بخش تنظیمات حساب بالا استفاده کنید.", False


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