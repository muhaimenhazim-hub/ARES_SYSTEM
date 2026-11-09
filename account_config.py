"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 5.0 (DIRECT METAAPI CLOUD DEPLOYMENT & REAL-BALANCE SYNC)
================================================================================
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Tuple, Optional

CONFIG_FILE = "ares_user_config.json"

META_API_TOKEN = os.getenv(
    "META_API_TOKEN",
    "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiI1NTNiOWZjNjNiOTIyNWNiNGVlYjM1ZWExOTkwZDVhZSIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVzdC1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcnBjLWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6d3M6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJtZXRhc3RhdHMtYXBpIiwibWV0aG9kcyI6WyJtZXRhc3RhdHMtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6InJpc2stbWFuYWdlbWVudC1hcGkiLCJtZXRob2RzIjpbInJpc2stbWFuYWdlbWVudC1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoiY29weWZhY3RvcnktYXBpIiwibWV0aG9kcyI6WyJjb3B5ZmFjdG9yeS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoibXQtbWFuYWdlci1hcGkiLCJtZXRob2RzIjpbIm10LW1hbmFnZXItYXBpOnJlc3Q6ZGVhbGluZzoqOioiLCJtdC1tYW5hZ2VyLWFwaTpyZXN0OnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJiaWxsaW5nLWFwaSIsIm1ldGhvZHMiOlsiYmlsbGluZy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiNTUzYjlmYzYzYjkyMjVjYjRlZWIzNWVhMTk5MGQ1YWUiLCJpYXQiOjE3OTQyMDUzMTV9.WREJro75xylp_XbGoXV8lY0rcoVCcW9-QDtMyySM1KCYLs1kRaCdSGsBcrb6XCNFVRDMdtAM9mRMGv0f1GIPHCZ2lhFayNMWZw52vlCOT-qTHkWNcoq4HwaNKY4hO46_wb7pUHoIGiZfgR7we2qUGHsfudYLnjWtKqkjrYZiz3RzPMog26uoxvxMM0tgFjXun8Wq75p71hpqyTtJOY9NtzWKCMacXyoJwMD_22BoMfUC5aOJ31laVKPktSmxjyA7tLboD3IRixA2z7s_ucoGK608E8CHiiFwGtncl90Zut0th_NBx52vtcnUAamZ_45TRzvfq3Tg8FlP0Znlft_jUPKQLVeVICHw0mA7OrbGOEWhmJ-Bbwj0X1KpG59B6jGJKkbZbwxcC3HG6J_tnfxZTusqvOwSlK5akveJGF44MAfBnbfzZBkCOD19M4T8rfE-J4-P0jeBGoMw9oxSLoZp3YCQEARpJmLfu6EjAJp7qkz24725pSPkKRgkzceALkCplt9qESaQ-nfU7JhF0ijeLWfkSK2C1o1veqxuvJHusL2wOaGa7rzERxu498HVkWmxBJycsjmUiQ3rqwPOnIFVk1aB7ydC2ruIGBjVg9Jk_2pv8eGMCgW8a1SAY763fjZDhI_eDQXBqnlxPRrV1YSeOxyzCqjYphtuLq8oZbo1S_s"
)

_METAAPI_ACCOUNT_CACHE: Dict[str, str] = {}


def _get_or_create_metaapi_account(login: str, password: str, server: str) -> Optional[str]:
    """ثبت و استقرار حساب متاتریدر در سرور ابری MetaApi"""
    if login in _METAAPI_ACCOUNT_CACHE:
        return _METAAPI_ACCOUNT_CACHE[login]

    headers = {
        "auth-token": META_API_TOKEN,
        "Content-Type": "application/json",
        "User-Agent": "AresTradingSystem/5.0"
    }

    try:
        # ۱. بررسی اینکه آیا اکانت قبلاً در متا اضافه شده است؟
        url_get = "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts"
        req = urllib.request.Request(url_get, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            accounts = json.loads(resp.read().decode())
            for acc in accounts:
                if str(acc.get("login")) == str(login):
                    acc_id = acc["id"]
                    _METAAPI_ACCOUNT_CACHE[login] = acc_id
                    # اطمینان از استقرار (Deploy)
                    if acc.get("state") != "DEPLOYED":
                        _deploy_metaapi_account(acc_id)
                    return acc_id

        # ۲. اگر نبود، ساخت اکانت جدید در سرور ابری
        payload = json.dumps({
            "name": f"Ares_{login}",
            "type": "cloud",
            "login": str(login),
            "password": password,
            "server": server,
            "platform": "mt5",
            "magic": 100088
        }).encode("utf-8")

        req_create = urllib.request.Request(url_get, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req_create, timeout=10.0) as resp:
            data = json.loads(resp.read().decode())
            acc_id = data.get("id")
            if acc_id:
                _METAAPI_ACCOUNT_CACHE[login] = acc_id
                _deploy_metaapi_account(acc_id)
                return acc_id
    except Exception as e:
        print(f"⚠️ خطای افزودن اکانت در MetaApi: {e}")
        return None

    return None


def _deploy_metaapi_account(account_id: str):
    """فرمان روشن شدن و اتصال سرور ابری به بروکر کاربر"""
    headers = {"auth-token": META_API_TOKEN, "User-Agent": "AresTradingSystem/5.0"}
    url = f"https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts/{account_id}/deploy"
    try:
        req = urllib.request.Request(url, data=b"{}", headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=5.0)
    except Exception:
        pass


def fetch_metaapi_balance(account_id: str) -> Tuple[float, str, str, bool]:
    """دریافت دقیق موجودی و وضعیت اتصال لحظه‌ای"""
    headers = {"auth-token": META_API_TOKEN, "User-Agent": "AresTradingSystem/5.0"}
    url = f"https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts/{account_id}/information"
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            info = json.loads(resp.read().decode())
            equity = float(info.get("equity", info.get("balance", 0.0)))
            broker = info.get("broker", "MetaQuotes")
            server = info.get("server", "Server")
            currency = info.get("currency", "USD")
            return equity, f"اکانت متاتریدر ۵ ({currency})", f"بروکر: {broker} | سرور: {server}", True
    except urllib.error.HTTPError as e:
        if e.code == 404 or e.code == 400:
            return 0.0, "اکانت متاتریدر ۵", "در حال استقرار ابری و اتصال به سرور بروکر...", False
        return 0.0, "اکانت متاتریدر ۵", f"خطای اتصال سرور (کد {e.code})", False
    except Exception:
        return 0.0, "اکانت متاتریدر ۵", "در حال برقراری ارتباط با بروکر...", False


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """محاسبه موجودی واقعی کاربر بدون هیچگونه دیتای فرضی"""
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    trading_mode = user_cfg.get("trading_mode", "PAPER")
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()

    m_login = str(user_cfg.get("mt5_login", "")).strip()
    m_pass = str(user_cfg.get("mt5_pass", "")).strip()
    m_server = str(user_cfg.get("mt5_server", "")).strip()

    # ۱. بررسی بایننس
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
            return 0.0, "خطای احراز بایننس", "کلیدهای API بایننس نامعتبر هستند.", False

    # ۲. بررسی متاتریدر ۵
    if m_login and m_pass and m_server:
        acc_id = _get_or_create_metaapi_account(m_login, m_pass, m_server)
        if acc_id:
            eq, acc_title, broker_desc, is_ok = fetch_metaapi_balance(acc_id)
            mode_label = "حساب دمو" if trading_mode == "PAPER" else "حساب واقعی"
            return eq, f"{acc_title} | {mode_label}", broker_desc, is_ok
        else:
            return 0.0, f"اکانت {m_login}", "در حال احراز هویت با سرور بروکر...", False

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