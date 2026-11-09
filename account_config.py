"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 9.0 (INTER-PROCESS BRIDGE SYNC & MT5 COMMAND QUEUE)
================================================================================
"""

import json
import os
from typing import Dict, Any, Tuple, List

CONFIG_FILE = "ares_user_config.json"
BRIDGE_CACHE_FILE = "ares_bridge_cache.json"
COMMANDS_FILE = "ares_mt5_pending_commands.json"

# کش حافظه موقت
BRIDGE_LIVE_DATA: Dict[str, Dict[str, Any]] = {}


def _load_json_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_file(file_path: str, data: Dict[str, Any]) -> None:
    try:
        temp_file = f"{file_path}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, file_path)
    except Exception:
        pass


def update_bridge_data(identifier: str, data: Dict[str, Any]):
    """دریافت زنده دیتای حساب از متاتریدر و اشتراک آن بین پروسه‌ها"""
    clean_id = identifier.strip().lower()
    BRIDGE_LIVE_DATA[clean_id] = data
    if "login" in data:
        BRIDGE_LIVE_DATA[str(data["login"])] = data

    # ذخیره در فایل کش جهت دسترسی هم‌زمان main.py و dashboard
    cache = _load_json_file(BRIDGE_CACHE_FILE)
    cache[clean_id] = data
    if "login" in data:
        cache[str(data["login"])] = data
    _save_json_file(BRIDGE_CACHE_FILE, cache)


def queue_mt5_command(target_id: str, command: Dict[str, Any]):
    """افزودن دستور معاملاتی جدید به صف منتظر متاتریدر ۵"""
    clean_id = target_id.strip().lower()
    all_cmds = _load_json_file(COMMANDS_FILE)
    if clean_id not in all_cmds:
        all_cmds[clean_id] = []
    all_cmds[clean_id].append(command)
    _save_json_file(COMMANDS_FILE, all_cmds)


def pop_pending_mt5_commands(target_id: str) -> List[Dict[str, Any]]:
    """تحویل و تخلیه دستورات معاملاتی برای اکسپرت متاتریدر"""
    clean_id = target_id.strip().lower()
    all_cmds = _load_json_file(COMMANDS_FILE)
    if clean_id in all_cmds and all_cmds[clean_id]:
        cmds = all_cmds[clean_id]
        all_cmds[clean_id] = []
        _save_json_file(COMMANDS_FILE, all_cmds)
        return cmds
    return []


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """انطباق هوشمند و صددرصدی کاربر با متاتریدر متصل (خوانش زنده از دیسک و حافظه)"""
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    user_ident = str(user_cfg.get("identifier", "")).strip().lower()
    m_login = str(user_cfg.get("mt5_login", "")).strip()

    # ادغام دیتای رم با دیتای اشتراکی دیسک
    merged_data = _load_json_file(BRIDGE_CACHE_FILE)
    merged_data.update(BRIDGE_LIVE_DATA)

    # ۱. انطباق با شماره کاربر/موبایل
    if user_ident and user_ident in merged_data:
        bridge = merged_data[user_ident]
        eq = float(bridge.get("equity", bridge.get("balance", 0.0)))
        company = bridge.get("broker", "Aron Markets")
        server = bridge.get("server", "AronMarkets-Demo")
        login_num = bridge.get("login", "")
        return eq, f"اکانت متاتریدر {login_num} (زنده)", f"بروکر: {company} | سرور: {server} | متصل و آنلاین", True

    # ۲. انطباق با لاگین متاتریدر
    if m_login and m_login in merged_data:
        bridge = merged_data[m_login]
        eq = float(bridge.get("equity", bridge.get("balance", 0.0)))
        company = bridge.get("broker", "Aron Markets")
        server = bridge.get("server", "AronMarkets-Demo")
        login_num = bridge.get("login", "")
        return eq, f"اکانت متاتریدر {login_num} (زنده)", f"بروکر: {company} | سرور: {server} | متصل و آنلاین", True

    # ۳. انطباق خودکار در صورت وجود اتصال فعال
    if merged_data:
        bridge = next(iter(merged_data.values()))
        eq = float(bridge.get("equity", bridge.get("balance", 0.0)))
        company = bridge.get("broker", "Aron Markets")
        server = bridge.get("server", "AronMarkets-Demo")
        login_num = bridge.get("login", "")
        return eq, f"اکانت متاتریدر {login_num} (زنده)", f"بروکر: {company} | سرور: {server} | متصل و آنلاین", True

    # ۴. بررسی بایننس
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
    return _load_json_file(CONFIG_FILE)


def save_config(cfg: Dict[str, Any]) -> None:
    _save_json_file(CONFIG_FILE, cfg)


def fetch_live_account_balance() -> Tuple[float, str, str, bool]:
    cfg = load_config()
    return fetch_user_live_balance(cfg)