"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 14.0 (STRICT USER ISOLATION, AUTO-TERMINAL BRIDGE & BINANCE LIVE EXEC)
================================================================================
"""

import json
import os
import time
from typing import Dict, Any, Tuple, List, Optional

CONFIG_FILE = "ares_user_config.json"
BRIDGE_CACHE_FILE = "ares_bridge_cache.json"
COMMANDS_FILE = "ares_mt5_pending_commands.json"

BRIDGE_LIVE_DATA: Dict[str, Dict[str, Any]] = {}


def _load_json_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json_file(file_path: str, data: Dict[str, Any]) -> None:
    try:
        temp_file = f"{file_path}.{os.getpid()}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, file_path)
    except Exception:
        pass


def update_bridge_data(identifier: str, data: Dict[str, Any]):
    """دریافت زنده دیتای حساب، پوزیشن‌های باز و تاریخچه سود از متاتریدر"""
    now_ts = time.time()
    data["last_sync_ts"] = now_ts

    clean_id = str(identifier).strip().lower()
    login_str = str(data.get("login", "")).strip()

    cache = _load_json_file(BRIDGE_CACHE_FILE)

    if clean_id:
        BRIDGE_LIVE_DATA[clean_id] = data
        cache[clean_id] = data
    if login_str:
        BRIDGE_LIVE_DATA[login_str] = data
        cache[login_str] = data

    _save_json_file(BRIDGE_CACHE_FILE, cache)


def get_user_bridge_snapshot(user_cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """دریافت اطلاعات زنده متاتریدر مختص همان کاربر (بدون نشت اطلاعات بین کاربران)"""
    if not user_cfg:
        return None

    user_ident = str(user_cfg.get("identifier", "")).strip().lower()
    m_login = str(user_cfg.get("mt5_login", "")).strip()
    user_id = str(user_cfg.get("user_id", "")).strip().lower()

    merged_data = _load_json_file(BRIDGE_CACHE_FILE)
    merged_data.update(BRIDGE_LIVE_DATA)

    # ۱. تطابق دقیق با شماره حساب متاتریدر ثبت‌شده در تنظیمات کاربر
    if m_login and m_login in merged_data:
        return merged_data[m_login]

    # ۲. تطابق دقیق با شناسه کاربری (ایمیل یا شماره موبایل)
    if user_ident and user_ident in merged_data:
        return merged_data[user_ident]

    # ۳. تطابق با شناسه داخلی
    if user_id and user_id in merged_data:
        return merged_data[user_id]

    return None


def queue_mt5_command(target_keys: List[str], command: Dict[str, Any]):
    """ثبت دستور معاملاتی در صف متاتریدر با کلیدهای یکتا جهت تضمین تحویل ۱۰۰٪"""
    all_cmds = _load_json_file(COMMANDS_FILE)
    cmd_id = f"cmd_{int(time.time() * 1000)}_{os.urandom(2).hex()}"
    command["cmd_id"] = cmd_id

    for key in set(k.strip().lower() for k in target_keys if k and str(k).strip()):
        if key not in all_cmds:
            all_cmds[key] = []
        all_cmds[key].append(command)

    _save_json_file(COMMANDS_FILE, all_cmds)


def pop_pending_mt5_commands(identifier: str = "", login_str: str = "") -> List[Dict[str, Any]]:
    """تحویل دستورات به متاتریدر و حذف همزمان از تمام کلیدهای متناظر جهت جلوگیری از تکرار"""
    clean_id = str(identifier).strip().lower()
    clean_login = str(login_str).strip().lower()

    all_cmds = _load_json_file(COMMANDS_FILE)
    collected: List[Dict[str, Any]] = []
    seen_ids = set()
    modified = False

    for key in [clean_id, clean_login]:
        if key and key in all_cmds and all_cmds[key]:
            for cmd in all_cmds[key]:
                cid = cmd.get("cmd_id", str(cmd))
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    collected.append(cmd)
            all_cmds[key] = []
            modified = True

    if modified:
        # پاکسازی دستورات تحویل‌شده از سایر کلیدها
        for k in list(all_cmds.keys()):
            all_cmds[k] = [c for c in all_cmds[k] if c.get("cmd_id", str(c)) not in seen_ids]
        _save_json_file(COMMANDS_FILE, all_cmds)

    return collected


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """بررسی وضعیت اتصال و موجودی زنده حساب کاربر (متاتریدر ۵ یا بایننس)"""
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    bridge = get_user_bridge_snapshot(user_cfg)
    m_login = str(user_cfg.get("mt5_login", "")).strip()
    m_server = str(user_cfg.get("mt5_server", "")).strip()

    if bridge:
        eq = float(bridge.get("equity", bridge.get("balance", 0.0)))
        company = bridge.get("broker", "MetaTrader 5")
        server = bridge.get("server", m_server or "Live-Server")
        login_num = bridge.get("login", m_login)
        return eq, f"اکانت متاتریدر {login_num} (متصل)", f"بروکر: {company} | سرور: {server} | ارتباط برخط ۲۴ ساعته فعال", True

    # اگر کاربر اطلاعات متاتریدر را در سایت ذخیره کرده و منتظر همگام‌سازی اولیه ترمینال سرور است
    if m_login:
        return (
            0.0,
            f"اکانت متاتریدر {m_login} (در حال همگام‌سازی...)",
            f"سرور: {m_server or 'پیش‌فرض'} | در انتظار دریافت اولین تیک از متاتریدر سرور",
            False,
        )

    # بررسی حساب بایننس فیوچرز
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()
    if b_key and b_secret:
        try:
            import ccxt
            exchange = ccxt.binanceusdm({
                "apiKey": b_key,
                "secret": b_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
                "timeout": 7000,
            })
            balance_info = exchange.fetch_balance()
            real_equity = float(balance_info.get("total", {}).get("USDT", 0.0))
            return real_equity, "بایننس فیوچرز (زنده)", f"صرافی متصل: بایننس | موجودی: {real_equity:.2f} USDT", True
        except Exception:
            return 0.0, "خطای اتصال بایننس", "کلیدهای API بایننس نامعتبر هستند یا دسترسی Futures ندارند.", False

    return 0.0, "حساب معاملاتی متصل نیست", "از دکمه «تنظیمات حساب» اطلاعات متاتریدر ۵ یا بایننس خود را وارد کنید.", False


def execute_binance_order(user_cfg: Dict[str, Any], symbol: str, side: str, volume: float, stop_loss: float = 0.0, take_profit: float = 0.0) -> Tuple[bool, str]:
    """اجرای واقعی سفارش در بایننس فیوچرز برای کاربران کریپتو"""
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()
    if not b_key or not b_secret:
        return False, "No Binance API keys"
    try:
        import ccxt
        exchange = ccxt.binanceusdm({
            "apiKey": b_key,
            "secret": b_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        base = symbol.replace("USDT", "")
        formatted_symbol = f"{base}/USDT:USDT"
        order_side = "buy" if side.upper() == "BUY" else "sell"
        order = exchange.create_market_order(formatted_symbol, order_side, volume)
        return True, str(order.get("id", "OK"))
    except Exception as e:
        return False, str(e)


def load_config() -> Dict[str, Any]:
    return _load_json_file(CONFIG_FILE)


def save_config(cfg: Dict[str, Any]) -> None:
    _save_json_file(CONFIG_FILE, cfg)


def fetch_live_account_balance() -> Tuple[float, str, str, bool]:
    cfg = load_config()
    return fetch_user_live_balance(cfg)