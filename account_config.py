"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 14.4 (QUEUE DEDUP, BINANCE REAL SL/TP ORDERS & LIVE POSITION SYNC)
================================================================================
"""

import json
import os
import time
from typing import Dict, Any, Tuple, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "ares_user_config.json")
BRIDGE_CACHE_FILE = os.path.join(BASE_DIR, "ares_bridge_cache.json")
COMMANDS_FILE = os.path.join(BASE_DIR, "ares_mt5_pending_commands.json")
COMMAND_TTL_SECONDS = 600.0

BRIDGE_LIVE_DATA: Dict[str, Dict[str, Any]] = {}

# جدول نگاشت نمادهای استاندارد تحلیل تکنیکال به اسامی مرسوم در انواع بروکرهای متاتریدر
BROKER_SYMBOL_ALIASES = {
    "EURUSD": ["EURUSD.", "EURUSD", "EURUSD_i", "EURUSDm", "EURUSD.pro", "EURUSDraw"],
    "XAUUSD": ["XAUUSD.", "XAUUSD", "GOLD", "GOLD.", "XAUUSD_i", "XAUUSDm", "GOLDm"],
    "NASDAQ 100": ["NAS100", "NAS100.", "USTEC", "USTEC.", "US100", "US100.", "NQ", "NQ=F", "NASDAQ"],
    "S&P 500": ["US500", "US500.", "SP500", "SP500.", "ES", "ES=F", "SPX500"],
}


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


def _prune_expired_commands(all_cmds: Dict[str, Any], ttl_seconds: float = COMMAND_TTL_SECONDS) -> Tuple[Dict[str, Any], bool]:
    """پاکسازی خودکار دستورات منقضی‌شده و کلیدهای خالی جهت جلوگیری از قفل دائمی صف"""
    now_ts = time.time()
    modified = False
    for key in list(all_cmds.keys()):
        cmds = all_cmds.get(key)
        if not isinstance(cmds, list) or not cmds:
            del all_cmds[key]
            modified = True
            continue
        fresh_cmds = [
            c for c in cmds
            if isinstance(c, dict) and (now_ts - float(c.get("created_ts", 0.0))) <= ttl_seconds
        ]
        if len(fresh_cmds) != len(cmds):
            modified = True
        if fresh_cmds:
            all_cmds[key] = fresh_cmds
        else:
            del all_cmds[key]
            modified = True
    return all_cmds, modified


def update_bridge_data(identifier: str, data: Dict[str, Any], extra_keys: Optional[List[str]] = None):
    """دریافت زنده دیتای حساب، پوزیشن‌های واقعی و لیست نمادهای فعال از متاتریدر"""
    now_ts = time.time()
    data["last_sync_ts"] = now_ts

    clean_id = str(identifier).strip().lower()
    login_str = str(data.get("login", "")).strip().lower()

    cache = _load_json_file(BRIDGE_CACHE_FILE)

    keys = {clean_id, login_str}
    if extra_keys:
        for ek in extra_keys:
            if ek and str(ek).strip():
                keys.add(str(ek).strip().lower())

    for k in keys:
        if k:
            BRIDGE_LIVE_DATA[k] = data
            cache[k] = data

    _save_json_file(BRIDGE_CACHE_FILE, cache)


def get_user_bridge_snapshot(user_cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """دریافت اطلاعات زنده متاتریدر مختص همان کاربر"""
    if not user_cfg:
        return None

    user_ident = str(user_cfg.get("identifier", "")).strip().lower()
    m_login = str(user_cfg.get("mt5_login", "")).strip()
    user_id = str(user_cfg.get("user_id", "")).strip().lower()

    merged_data = _load_json_file(BRIDGE_CACHE_FILE)
    merged_data.update(BRIDGE_LIVE_DATA)

    if m_login and m_login in merged_data:
        return merged_data[m_login]

    if user_ident and user_ident in merged_data:
        return merged_data[user_ident]

    if user_id and user_id in merged_data:
        return merged_data[user_id]

    return None


def resolve_broker_symbol(canonical_symbol: str, user_cfg: Optional[Dict[str, Any]] = None) -> str:
    """
    شناسایی خودکار و هوشمند پسوند/پیشوند بروکر کاربر.
    """
    clean_sym = canonical_symbol.strip()
    aliases = BROKER_SYMBOL_ALIASES.get(clean_sym, [clean_sym])

    bridge = get_user_bridge_snapshot(user_cfg) if user_cfg else None
    if bridge:
        known_symbols = list(bridge.get("active_symbols", []))
        if "open_positions" in bridge and isinstance(bridge["open_positions"], list):
            known_symbols.extend([p.get("symbol") for p in bridge["open_positions"] if p.get("symbol")])

        for alias in aliases:
            for s in known_symbols:
                if str(s).strip().upper() == alias.upper():
                    return str(s).strip()

        broker_name = str(bridge.get("broker", "")).lower()
        server_name = str(bridge.get("server", "")).lower()
        if "aron" in broker_name or "aron" in server_name:
            if clean_sym in ["EURUSD", "XAUUSD"]:
                return f"{clean_sym}."

    return aliases[0]


def get_user_pending_commands_count(target_keys: List[str]) -> int:
    """شمارش سفارشات منتظر در صف برای جلوگیری از ارسال مازاد بر ۳ پوزیشن"""
    all_cmds, modified = _prune_expired_commands(_load_json_file(COMMANDS_FILE))
    if modified:
        _save_json_file(COMMANDS_FILE, all_cmds)
    unique_cmd_ids = set()
    for key in set(k.strip().lower() for k in target_keys if k and str(k).strip()):
        for cmd in all_cmds.get(key, []):
            if cmd.get("action") in ["BUY", "SELL"]:
                cid = cmd.get("cmd_id", str(cmd))
                unique_cmd_ids.add(cid)
    return len(unique_cmd_ids)


def is_symbol_in_pending_queue(target_keys: List[str], symbol: str) -> bool:
    """بررسی اینکه آیا سفارشی برای این نماد در صف منتظر اجرا است یا خیر"""
    all_cmds, modified = _prune_expired_commands(_load_json_file(COMMANDS_FILE))
    if modified:
        _save_json_file(COMMANDS_FILE, all_cmds)
    clean_target = symbol.replace(" ", "").replace(".", "").upper()
    for key in set(k.strip().lower() for k in target_keys if k and str(k).strip()):
        for cmd in all_cmds.get(key, []):
            cmd_sym = str(cmd.get("symbol", cmd.get("broker_symbol", ""))).replace(" ", "").replace(".", "").upper()
            if cmd_sym == clean_target and cmd.get("action") in ["BUY", "SELL"]:
                return True
    return False


def queue_mt5_command(target_keys: List[str], command: Dict[str, Any], user_cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    ثبت دستور معاملاتی با اعمال فیلتر سخت‌گیرانه ضدتکرار (Anti-Duplication) و سقف‌گذاری قطعی حداکثر ۳ سفارش در صف
    """
    all_cmds, modified = _prune_expired_commands(_load_json_file(COMMANDS_FILE))
    if modified:
        _save_json_file(COMMANDS_FILE, all_cmds)

    clean_keys = set(k.strip().lower() for k in target_keys if k and str(k).strip())
    if not clean_keys:
        return False

    action = command.get("action", "").upper()

    # تبدیل نماد تحلیل تکنیکال به نماد اجرایی بروکر
    if "symbol" in command:
        command["broker_symbol"] = resolve_broker_symbol(command["symbol"], user_cfg)

    target_sym = str(command.get("broker_symbol", command.get("symbol", ""))).strip().upper()

    # ۱. فیلتر ضدتکرار و سقف ظرفیت برای سفارشات ورود (BUY / SELL)
    if action in ["BUY", "SELL"]:
        current_pending = get_user_pending_commands_count(list(clean_keys))
        if current_pending >= 3:
            print(f"🛑 [رد سفارش صف]: سقف ۳ سفارش همزمان در صف پر است.", flush=True)
            return False

        if is_symbol_in_pending_queue(list(clean_keys), target_sym):
            print(f"🛑 [رد سفارش تکراری]: دستور معاملاتی برای نماد {target_sym} قبلاً در صف ثبت شده و منتظر اجراست.", flush=True)
            return False

    now_ts = time.time()
    cmd_id = f"cmd_{int(now_ts * 1000)}_{os.urandom(2).hex()}"
    command["cmd_id"] = cmd_id
    command["created_ts"] = now_ts

    for key in clean_keys:
        if key not in all_cmds:
            all_cmds[key] = []
        all_cmds[key].append(command)

    _save_json_file(COMMANDS_FILE, all_cmds)
    return True


def pop_pending_mt5_commands(
    identifier: str = "",
    login_str: str = "",
    extra_keys: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """تحویل دستورات به متاتریدر و پاکسازی کامل از تمامی کلیدهای مرتبط با کاربر"""
    clean_id = str(identifier).strip().lower()
    clean_login = str(login_str).strip().lower()

    keys_to_pop = [k for k in [clean_id, clean_login] if k]
    if extra_keys:
        for ek in extra_keys:
            cek = str(ek).strip().lower()
            if cek and cek not in keys_to_pop:
                keys_to_pop.append(cek)

    all_cmds, modified = _prune_expired_commands(_load_json_file(COMMANDS_FILE))
    collected: List[Dict[str, Any]] = []
    seen_ids = set()

    for key in keys_to_pop:
        if key in all_cmds and all_cmds[key]:
            for cmd in all_cmds[key]:
                cid = cmd.get("cmd_id", str(cmd))
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    collected.append(cmd)
            del all_cmds[key]
            modified = True

    if seen_ids:
        for k in list(all_cmds.keys()):
            remaining = [c for c in all_cmds[k] if c.get("cmd_id", str(c)) not in seen_ids]
            if remaining:
                all_cmds[k] = remaining
            else:
                del all_cmds[k]
            modified = True

    if modified:
        _save_json_file(COMMANDS_FILE, all_cmds)

    return collected


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """بررسی وضعیت اتصال و خواندن دقیق موجودی زنده از متاتریدر یا بایننس"""
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

    if m_login:
        return (
            0.0,
            f"اکانت متاتریدر {m_login} (در حال همگام‌سازی...)",
            f"سرور: {m_server or 'پیش‌فرض'} | در انتظار دریافت اولین تیک از متاتریدر",
            False,
        )

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
            return 0.0, "خطای اتصال بایننس", "کلیدهای API بایننس نامعتبر هستند.", False

    return 0.0, "حساب معاملاتی متصل نیست", "از دکمه «تنظیمات حساب» اطلاعات متاتریدر ۵ یا بایننس خود را وارد کنید.", False


def _create_binance_exchange(user_cfg: Dict[str, Any]):
    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()
    if not b_key or not b_secret:
        return None
    import ccxt
    return ccxt.binanceusdm({
        "apiKey": b_key,
        "secret": b_secret,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
        "timeout": 10000,
    })


def _format_binance_symbol(symbol: str) -> str:
    clean = symbol.replace("/", "").replace(":USDT", "").replace("USDT", "").strip().upper()
    return f"{clean}/USDT:USDT"


def execute_binance_order_detailed(
    user_cfg: Dict[str, Any],
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    sl_dist: float = 0.0,
    tp_dist: float = 0.0,
) -> Dict[str, Any]:
    """اجرای سفارش بازار بایننس همراه با ثبت واقعی STOP_MARKET (SL) و TAKE_PROFIT_MARKET (TP) با نسبت ۱ به ۱.۵"""
    exchange = _create_binance_exchange(user_cfg)
    if exchange is None:
        return {"success": False, "error": "No Binance API keys"}

    try:
        exchange.load_markets()
        formatted_symbol = _format_binance_symbol(symbol)
        is_buy = side.upper() == "BUY"
        order_side = "buy" if is_buy else "sell"
        close_side = "sell" if is_buy else "buy"

        exec_vol = float(exchange.amount_to_precision(formatted_symbol, volume))
        order = exchange.create_market_order(formatted_symbol, order_side, exec_vol)
        order_id = str(order.get("id", "OK"))

        real_entry = float(order.get("average") or order.get("price") or 0.0)
        if real_entry <= 0:
            ticker = exchange.fetch_ticker(formatted_symbol)
            real_entry = float(ticker.get("last") or 0.0)

        # محاسبه دقیق SL و TP نسبت به قیمت واقعی پرشدن سفارش در بایننس
        eff_sl_dist = float(sl_dist)
        if eff_sl_dist <= 0 and stop_loss > 0 and real_entry > 0:
            eff_sl_dist = abs(real_entry - float(stop_loss))

        eff_tp_dist = float(tp_dist)
        if eff_tp_dist <= 0 and eff_sl_dist > 0:
            eff_tp_dist = eff_sl_dist * 1.5

        real_sl = float(stop_loss)
        real_tp = float(take_profit)
        if eff_sl_dist > 0 and real_entry > 0:
            real_sl = (real_entry - eff_sl_dist) if is_buy else (real_entry + eff_sl_dist)
            real_tp = (real_entry + eff_tp_dist) if is_buy else (real_entry - eff_tp_dist)

        sl_order_id = ""
        tp_order_id = ""

        if real_sl > 0:
            try:
                sl_price = float(exchange.price_to_precision(formatted_symbol, real_sl))
                sl_res = exchange.create_order(
                    formatted_symbol,
                    "STOP_MARKET",
                    close_side,
                    exec_vol,
                    None,
                    {"stopPrice": sl_price, "reduceOnly": True},
                )
                sl_order_id = str(sl_res.get("id", ""))
                real_sl = sl_price
            except Exception as sl_err:
                print(f"⚠️ [هشدار ثبت SL بایننس برای {symbol}]: {sl_err}", flush=True)

        if real_tp > 0:
            try:
                tp_price = float(exchange.price_to_precision(formatted_symbol, real_tp))
                tp_res = exchange.create_order(
                    formatted_symbol,
                    "TAKE_PROFIT_MARKET",
                    close_side,
                    exec_vol,
                    None,
                    {"stopPrice": tp_price, "reduceOnly": True},
                )
                tp_order_id = str(tp_res.get("id", ""))
                real_tp = tp_price
            except Exception as tp_err:
                print(f"⚠️ [هشدار ثبت TP بایننس برای {symbol}]: {tp_err}", flush=True)

        return {
            "success": True,
            "order_id": order_id,
            "entry_price": real_entry,
            "volume": exec_vol,
            "stop_loss": real_sl,
            "take_profit": real_tp,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "error": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def execute_binance_order(
    user_cfg: Dict[str, Any],
    symbol: str,
    side: str,
    volume: float,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
) -> Tuple[bool, str]:
    res = execute_binance_order_detailed(
        user_cfg=user_cfg,
        symbol=symbol,
        side=side,
        volume=volume,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    if res.get("success"):
        return True, str(res.get("order_id", "OK"))
    return False, str(res.get("error", "Unknown error"))


def fetch_binance_open_positions(user_cfg: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """دریافت لیست پوزیشن‌های واقعاً باز در بایننس فیوچرز برای همگام‌سازی دیتابیس"""
    exchange = _create_binance_exchange(user_cfg)
    if exchange is None:
        return None
    try:
        positions = exchange.fetch_positions()
        active: List[Dict[str, Any]] = []
        for p in positions:
            contracts = float(p.get("contracts") or p.get("info", {}).get("positionAmt") or 0.0)
            if abs(contracts) <= 0:
                continue
            raw_sym = str(p.get("symbol", "")).split(":")[0].replace("/", "")
            side_str = str(p.get("side", "")).upper()
            if side_str not in ("BUY", "SELL"):
                side_str = "BUY" if contracts > 0 else "SELL"
            active.append({
                "symbol": raw_sym,
                "side": side_str,
                "volume": abs(contracts),
                "entry_price": float(p.get("entryPrice") or 0.0),
                "unrealized_pnl": float(p.get("unrealizedPnl") or 0.0),
            })
        return active
    except Exception:
        return None


def update_binance_sl_to_breakeven(
    user_cfg: Dict[str, Any],
    symbol: str,
    side: str,
    volume: float,
    new_sl: float,
) -> bool:
    """به‌روزرسانی حد ضرر بایننس (مثلاً انتقال به Break-Even)"""
    exchange = _create_binance_exchange(user_cfg)
    if exchange is None:
        return False
    try:
        exchange.load_markets()
        formatted_symbol = _format_binance_symbol(symbol)
        close_side = "sell" if side.upper() == "BUY" else "buy"
        open_orders = exchange.fetch_open_orders(formatted_symbol)
        for o in open_orders:
            o_type = str(o.get("type", "")).upper()
            if "STOP" in o_type and "TAKE_PROFIT" not in o_type:
                try:
                    exchange.cancel_order(o["id"], formatted_symbol)
                except Exception:
                    pass
        exec_vol = float(exchange.amount_to_precision(formatted_symbol, volume))
        sl_price = float(exchange.price_to_precision(formatted_symbol, new_sl))
        exchange.create_order(
            formatted_symbol,
            "STOP_MARKET",
            close_side,
            exec_vol,
            None,
            {"stopPrice": sl_price, "reduceOnly": True},
        )
        return True
    except Exception:
        return False


def close_binance_position(
    user_cfg: Dict[str, Any],
    symbol: str,
    side: str,
    volume: float,
) -> bool:
    """بستن کامل پوزیشن بایننس و پاکسازی سفارش‌های باز SL/TP آن نماد"""
    exchange = _create_binance_exchange(user_cfg)
    if exchange is None:
        return False
    try:
        exchange.load_markets()
        formatted_symbol = _format_binance_symbol(symbol)
        close_side = "sell" if side.upper() == "BUY" else "buy"
        try:
            exchange.cancel_all_orders(formatted_symbol)
        except Exception:
            pass
        exec_vol = float(exchange.amount_to_precision(formatted_symbol, volume))
        if exec_vol > 0:
            exchange.create_market_order(
                formatted_symbol,
                close_side,
                exec_vol,
                params={"reduceOnly": True},
            )
        return True
    except Exception:
        return False


def load_config() -> Dict[str, Any]:
    return _load_json_file(CONFIG_FILE)


def save_config(cfg: Dict[str, Any]) -> None:
    _save_json_file(CONFIG_FILE, cfg)


def fetch_live_account_balance() -> Tuple[float, str, str, bool]:
    cfg = load_config()
    return fetch_user_live_balance(cfg)