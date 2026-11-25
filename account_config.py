"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 14.8 (ATOMIC SQLITE MT5 COMMAND QUEUE + ACK DELIVERY GUARANTEE)
================================================================================
"""

import json
import os
import sqlite3
import threading
import time
from typing import Dict, Any, Tuple, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "ares_user_config.json")
BRIDGE_CACHE_FILE = os.path.join(BASE_DIR, "ares_bridge_cache.json")
COMMANDS_FILE = os.path.join(BASE_DIR, "ares_mt5_pending_commands.json")
DB_FILE = os.path.join(BASE_DIR, "ares_trading.db")
COMMAND_TTL_SECONDS = 600.0
RESEND_COOLDOWN_SECONDS = 6.0
BRIDGE_STALE_SECONDS = 45.0
BINANCE_BALANCE_CACHE_TTL = 8.0

BRIDGE_LIVE_DATA: Dict[str, Dict[str, Any]] = {}
_BINANCE_BALANCE_CACHE: Dict[str, Tuple[float, Tuple[float, str, str, bool]]] = {}
_QUEUE_INIT_LOCK = threading.Lock()
_QUEUE_DB_READY = False

# جدول نگاشت نمادهای استاندارد تحلیل تکنیکال به اسامی مرسوم در انواع بروکرهای متاتریدر
BROKER_SYMBOL_ALIASES = {
    "EURUSD": ["EURUSD.", "EURUSD", "EURUSD_i", "EURUSDm", "EURUSD.pro", "EURUSDraw", "EURUSD.a"],
    "XAUUSD": ["XAUUSD.", "XAUUSD", "GOLD", "GOLD.", "XAUUSD_i", "XAUUSDm", "GOLDm", "XAUUSD.a"],
    "NASDAQ 100": [
        "NAS100", "NAS100.", "USTEC", "USTEC.", "US100", "US100.",
        "NDX100", "NDXUSD", "NDXUSD.", "NDX", "US100Cash", "NAS100_i", "NAS100m", "NQ", "NQ=F", "NASDAQ",
    ],
    "S&P 500": [
        "US500", "US500.", "SP500", "SP500.", "SPX500", "SPX500.",
        "SPXUSD", "SPXUSD.", "SPX", "US500Cash", "US500_i", "US500m", "ES", "ES=F",
    ],
}


def _symbol_matches_alias(broker_sym: str, alias: str, allow_prefix: bool = True) -> bool:
    """تطبیق دقیق نماد بروکر بدون اشتباه گرفتن ETFهایی مثل SPXC/SPXL با شاخص S&P 500 یا NASDAQ"""
    su = str(broker_sym).strip().upper()
    au = str(alias).strip().upper()
    ac = au.rstrip(".")
    if not su or not ac:
        return False
    if su == au or su.rstrip(".") == ac:
        return True
    if not allow_prefix or len(ac) < 3:
        return False
    if ac in ("SPX", "NDX"):
        if not su.startswith(ac) or len(su) <= len(ac):
            return False
        rest = su[len(ac):]
        return (
            rest[0] in (".", "_", "-", "/")
            or rest[0].isdigit()
            or rest.startswith("USD")
            or rest.startswith("EUR")
            or rest.startswith("CASH")
            or rest.startswith("MINI")
        )
    if ac == "GOLD":
        if not su.startswith("GOLD") or len(su) <= 4:
            return False
        rest = su[4:]
        return (
            rest[0] in (".", "_", "-", "/")
            or rest in ("M", "I", "PRO", "RAW", "MICRO", "MINI", "CASH")
            or rest.startswith("USD")
        )
    return su.startswith(ac)


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


def _ensure_queue_db() -> None:
    global _QUEUE_DB_READY
    if _QUEUE_DB_READY:
        return
    with _QUEUE_INIT_LOCK:
        if _QUEUE_DB_READY:
            return
        conn = sqlite3.connect(DB_FILE, timeout=30.0, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA busy_timeout = 30000;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mt5_command_queue (
                    cmd_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    broker_symbol TEXT DEFAULT '',
                    payload_json TEXT NOT NULL,
                    created_ts REAL NOT NULL,
                    last_sent_ts REAL DEFAULT 0.0
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mt5_command_keys (
                    cmd_id TEXT NOT NULL,
                    routing_key TEXT NOT NULL,
                    PRIMARY KEY (cmd_id, routing_key)
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cmd_keys_key ON mt5_command_keys(routing_key);")
            _QUEUE_DB_READY = True
        finally:
            conn.close()


def _get_queue_conn() -> sqlite3.Connection:
    _ensure_queue_db()
    conn = sqlite3.connect(DB_FILE, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


def _clean_symbol_key(sym: str) -> str:
    return str(sym or "").replace(" ", "").replace(".", "").upper()


def _prune_expired_queue_rows(cur: sqlite3.Cursor, now_ts: float, ttl_seconds: float = COMMAND_TTL_SECONDS) -> None:
    cutoff = now_ts - ttl_seconds
    cur.execute(
        "DELETE FROM mt5_command_keys WHERE cmd_id IN (SELECT cmd_id FROM mt5_command_queue WHERE created_ts < ?);",
        (cutoff,),
    )
    cur.execute("DELETE FROM mt5_command_queue WHERE created_ts < ?;", (cutoff,))


def update_bridge_data(identifier: str, data: Dict[str, Any], extra_keys: Optional[List[str]] = None):
    """دریافت زنده دیتای حساب، پوزیشن‌های واقعی و لیست نمادهای فعال از متاتریدر"""
    if not isinstance(data, dict):
        return

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
        if k and k != "0":
            BRIDGE_LIVE_DATA[k] = data
            cache[k] = data

    _save_json_file(BRIDGE_CACHE_FILE, cache)


def clear_user_bridge_cache(keys: List[str]) -> None:
    """پاکسازی کامل کش زنده، فایل کش دیسک و صف دستورات معلق هنگام قطع ارتباط یا تغییر حساب"""
    clean_keys = sorted({str(k).strip().lower() for k in keys if k and str(k).strip()})
    if not clean_keys:
        return

    for k in list(BRIDGE_LIVE_DATA.keys()):
        if str(k).strip().lower() in clean_keys:
            del BRIDGE_LIVE_DATA[k]

    cache = _load_json_file(BRIDGE_CACHE_FILE)
    cache_modified = False
    for k in list(cache.keys()):
        if str(k).strip().lower() in clean_keys:
            del cache[k]
            cache_modified = True
    if cache_modified:
        _save_json_file(BRIDGE_CACHE_FILE, cache)

    all_cmds = _load_json_file(COMMANDS_FILE)
    cmds_modified = False
    for k in list(all_cmds.keys()):
        if str(k).strip().lower() in clean_keys:
            del all_cmds[k]
            cmds_modified = True
    if cmds_modified:
        _save_json_file(COMMANDS_FILE, all_cmds)

    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            ph = ",".join("?" for _ in clean_keys)
            cur.execute(f"DELETE FROM mt5_command_keys WHERE routing_key IN ({ph});", clean_keys)
            cur.execute("DELETE FROM mt5_command_queue WHERE cmd_id NOT IN (SELECT DISTINCT cmd_id FROM mt5_command_keys);")
            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطا در پاکسازی صف دیتابیس]: {e}", flush=True)


def get_user_bridge_snapshot(user_cfg: Dict[str, Any], allow_stale: bool = False) -> Optional[Dict[str, Any]]:
    """دریافت اطلاعات زنده متاتریدر مختص همان کاربر همراه با بررسی تازگی زمان همگام‌سازی"""
    if not user_cfg:
        return None

    user_ident = str(user_cfg.get("identifier", "")).strip().lower()
    m_login = str(user_cfg.get("mt5_login", "")).strip().lower()
    user_id = str(user_cfg.get("user_id", "")).strip().lower()

    merged_data = _load_json_file(BRIDGE_CACHE_FILE)
    merged_data.update(BRIDGE_LIVE_DATA)

    def _is_fresh(snap: Any) -> bool:
        if not isinstance(snap, dict):
            return False
        if allow_stale:
            return True
        ts = float(snap.get("last_sync_ts", 0.0) or 0.0)
        return ts > 0.0 and (time.time() - ts) <= BRIDGE_STALE_SECONDS

    for lookup_key in (m_login, user_ident, user_id):
        if lookup_key and lookup_key in merged_data:
            snap = merged_data[lookup_key]
            if _is_fresh(snap):
                return snap

    return None


def is_symbol_tradable_for_user(canonical_symbol: str, user_cfg: Optional[Dict[str, Any]] = None) -> bool:
    """بررسی اینکه آیا نماد در لیست نمادهای واقعی و قابل معامله بروکر کاربر فعال است یا خیر"""
    if not user_cfg:
        return True
    bridge = get_user_bridge_snapshot(user_cfg, allow_stale=True)
    if not bridge or not bridge.get("verified_symbols"):
        return True
    active_syms = bridge.get("active_symbols")
    if not isinstance(active_syms, list):
        return True

    clean_sym = canonical_symbol.strip()
    aliases = BROKER_SYMBOL_ALIASES.get(clean_sym, [clean_sym])
    for alias in aliases:
        for s in active_syms:
            if _symbol_matches_alias(str(s), alias, allow_prefix=True):
                return True
    return False


def resolve_broker_symbol(canonical_symbol: str, user_cfg: Optional[Dict[str, Any]] = None) -> str:
    """
    شناسایی خودکار و هوشمند پسوند/پیشوند بروکر کاربر با اولویت لیست نمادهای واقعی بروکر.
    """
    clean_sym = canonical_symbol.strip()
    aliases = BROKER_SYMBOL_ALIASES.get(clean_sym, [clean_sym])

    bridge = get_user_bridge_snapshot(user_cfg, allow_stale=True) if user_cfg else None
    if bridge:
        known_symbols: List[str] = []
        for s in bridge.get("active_symbols", []):
            if s and str(s).strip():
                known_symbols.append(str(s).strip())
        if "open_positions" in bridge and isinstance(bridge["open_positions"], list):
            for p in bridge["open_positions"]:
                if isinstance(p, dict) and p.get("symbol"):
                    known_symbols.append(str(p["symbol"]).strip())

        # ۱. تطبیق دقیق (حساس به حروف بزرگ/کوچک نیست)
        for alias in aliases:
            for s in known_symbols:
                if _symbol_matches_alias(s, alias, allow_prefix=False):
                    return s

        # ۲. تطبیق پیشوندی ایمن (برای نمادهایی با پسوندهای خاص مثل NAS100.c یا SPXUSD.)
        for alias in aliases:
            for s in known_symbols:
                if _symbol_matches_alias(s, alias, allow_prefix=True):
                    return s

        broker_name = str(bridge.get("broker", "")).lower()
        server_name = str(bridge.get("server", "")).lower()
        if "aron" in broker_name or "aron" in server_name:
            if clean_sym in ["EURUSD", "XAUUSD"]:
                return f"{clean_sym}."

    return aliases[0]


def get_user_pending_commands_count(target_keys: List[str]) -> int:
    """شمارش سفارشات منتظر در صف اتمیک دیتابیس برای جلوگیری از ارسال مازاد بر ۳ پوزیشن"""
    clean_keys = sorted({k.strip().lower() for k in target_keys if k and str(k).strip()})
    if not clean_keys:
        return 0
    now_ts = time.time()
    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            _prune_expired_queue_rows(cur, now_ts)
            ph = ",".join("?" for _ in clean_keys)
            cnt = cur.execute(
                f"SELECT COUNT(DISTINCT q.cmd_id) FROM mt5_command_queue q "
                f"JOIN mt5_command_keys k ON q.cmd_id = k.cmd_id "
                f"WHERE q.action IN ('BUY', 'SELL') AND k.routing_key IN ({ph});",
                clean_keys,
            ).fetchone()[0]
            conn.execute("COMMIT;")
            return int(cnt)
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطای شمارش صف MT5]: {e}", flush=True)
        return 0


def is_symbol_in_pending_queue(target_keys: List[str], symbol: str) -> bool:
    """بررسی اینکه آیا سفارشی برای این نماد در صف اتمیک منتظر اجرا است یا خیر"""
    clean_keys = sorted({k.strip().lower() for k in target_keys if k and str(k).strip()})
    clean_target = _clean_symbol_key(symbol)
    if not clean_keys or not clean_target:
        return False
    now_ts = time.time()
    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            _prune_expired_queue_rows(cur, now_ts)
            ph = ",".join("?" for _ in clean_keys)
            rows = cur.execute(
                f"SELECT DISTINCT q.broker_symbol FROM mt5_command_queue q "
                f"JOIN mt5_command_keys k ON q.cmd_id = k.cmd_id "
                f"WHERE q.action IN ('BUY', 'SELL') AND k.routing_key IN ({ph});",
                clean_keys,
            ).fetchall()
            conn.execute("COMMIT;")
            return any(_clean_symbol_key(r[0]) == clean_target for r in rows)
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطای بررسی نماد در صف MT5]: {e}", flush=True)
        return False


def queue_mt5_command(target_keys: List[str], command: Dict[str, Any], user_cfg: Optional[Dict[str, Any]] = None) -> bool:
    """
    ثبت اتمیک دستور معاملاتی در جدول صف SQLite با فیلتر سخت‌گیرانه ضدتکرار و سقف ۳ سفارش
    """
    clean_keys = sorted({k.strip().lower() for k in target_keys if k and str(k).strip()})
    if not clean_keys:
        return False

    action = str(command.get("action", "")).upper()

    if "symbol" in command:
        command["broker_symbol"] = resolve_broker_symbol(command["symbol"], user_cfg)

    target_sym = str(command.get("broker_symbol", command.get("symbol", ""))).strip().upper()
    now_ts = time.time()

    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            _prune_expired_queue_rows(cur, now_ts)
            ph = ",".join("?" for _ in clean_keys)

            if action in ("BUY", "SELL"):
                rows = cur.execute(
                    f"SELECT DISTINCT q.cmd_id, q.broker_symbol FROM mt5_command_queue q "
                    f"JOIN mt5_command_keys k ON q.cmd_id = k.cmd_id "
                    f"WHERE q.action IN ('BUY', 'SELL') AND k.routing_key IN ({ph});",
                    clean_keys,
                ).fetchall()
                if len(rows) >= 3:
                    conn.execute("COMMIT;")
                    print("🛑 [رد سفارش صف]: سقف ۳ سفارش همزمان در صف پر است.", flush=True)
                    return False

                clean_target = _clean_symbol_key(target_sym)
                if any(_clean_symbol_key(r[1]) == clean_target for r in rows):
                    conn.execute("COMMIT;")
                    print(f"🛑 [رد سفارش تکراری]: دستور معاملاتی برای نماد {target_sym} قبلاً در صف ثبت شده و منتظر اجراست.", flush=True)
                    return False

            cmd_id = f"cmd_{int(now_ts * 1000)}_{os.urandom(3).hex()}"
            payload = dict(command)
            payload["cmd_id"] = cmd_id
            payload["created_ts"] = now_ts

            cur.execute(
                "INSERT INTO mt5_command_queue (cmd_id, action, broker_symbol, payload_json, created_ts, last_sent_ts) "
                "VALUES (?, ?, ?, ?, ?, 0.0);",
                (cmd_id, action, target_sym, json.dumps(payload, ensure_ascii=False), now_ts),
            )
            cur.executemany(
                "INSERT INTO mt5_command_keys (cmd_id, routing_key) VALUES (?, ?);",
                [(cmd_id, key) for key in clean_keys],
            )
            conn.execute("COMMIT;")
            return True
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطای ثبت دستور در صف MT5]: {e}", flush=True)
        return False


def ack_mt5_commands(cmd_ids: List[str]) -> int:
    """حذف قطعی دستورات پس از دریافت تاییدیه تحویل (ACK) از متاتریدر"""
    ids = sorted({str(x).strip() for x in (cmd_ids or []) if x and str(x).strip()})
    if not ids:
        return 0
    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            ph = ",".join("?" for _ in ids)
            cur.execute(f"DELETE FROM mt5_command_keys WHERE cmd_id IN ({ph});", ids)
            cur.execute(f"DELETE FROM mt5_command_queue WHERE cmd_id IN ({ph});", ids)
            deleted = cur.rowcount
            conn.execute("COMMIT;")
            return int(deleted)
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطای ثبت ACK صف MT5]: {e}", flush=True)
        return 0


def pop_pending_mt5_commands(
    identifier: str = "",
    login_str: str = "",
    extra_keys: Optional[List[str]] = None,
    resend_cooldown: float = RESEND_COOLDOWN_SECONDS,
) -> List[Dict[str, Any]]:
    """تحویل دستورات به متاتریدر بدون پاک کردن زودهنگام (تا زمان دریافت ACK یا انقضا)"""
    clean_id = str(identifier).strip().lower()
    clean_login = str(login_str).strip().lower()

    keys_to_pop = [k for k in [clean_id, clean_login] if k]
    if extra_keys:
        for ek in extra_keys:
            cek = str(ek).strip().lower()
            if cek and cek not in keys_to_pop:
                keys_to_pop.append(cek)
    keys_to_pop = sorted(set(keys_to_pop))
    if not keys_to_pop:
        return []

    now_ts = time.time()
    try:
        conn = _get_queue_conn()
        try:
            conn.execute("BEGIN IMMEDIATE;")
            cur = conn.cursor()
            _prune_expired_queue_rows(cur, now_ts)
            ph = ",".join("?" for _ in keys_to_pop)
            rows = cur.execute(
                f"SELECT DISTINCT q.cmd_id, q.payload_json FROM mt5_command_queue q "
                f"JOIN mt5_command_keys k ON q.cmd_id = k.cmd_id "
                f"WHERE k.routing_key IN ({ph}) "
                f"AND (q.last_sent_ts = 0.0 OR (? - q.last_sent_ts) >= ?) "
                f"ORDER BY q.created_ts ASC;",
                keys_to_pop + [now_ts, float(resend_cooldown)],
            ).fetchall()
            if rows:
                ids = [r[0] for r in rows]
                iph = ",".join("?" for _ in ids)
                cur.execute(f"UPDATE mt5_command_queue SET last_sent_ts = ? WHERE cmd_id IN ({iph});", [now_ts] + ids)
            conn.execute("COMMIT;")
            return [json.loads(r[1]) for r in rows]
        except Exception:
            conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ [خطای خواندن صف MT5]: {e}", flush=True)
        return []


def fetch_user_live_balance(user_cfg: Dict[str, Any]) -> Tuple[float, str, str, bool]:
    """بررسی وضعیت اتصال و خواندن دقیق موجودی زنده از متاتریدر یا بایننس (همراه با گارد قطع ارتباط و کش بایننس)"""
    if not user_cfg:
        return 0.0, "حساب متصل نیست", "جهت اتصال از بخش تنظیمات حساب استفاده کنید.", False

    bridge = get_user_bridge_snapshot(user_cfg, allow_stale=False)
    m_login = str(user_cfg.get("mt5_login", "")).strip()
    m_server = str(user_cfg.get("mt5_server", "")).strip()

    if bridge:
        eq = float(bridge.get("equity", bridge.get("balance", 0.0)))
        company = bridge.get("broker", "MetaTrader 5")
        server = bridge.get("server", m_server or "Live-Server")
        login_num = bridge.get("login", m_login)
        return eq, f"اکانت متاتریدر {login_num} (متصل)", f"بروکر: {company} | سرور: {server} | ارتباط برخط ۲۴ ساعته فعال", True

    if m_login:
        stale_bridge = get_user_bridge_snapshot(user_cfg, allow_stale=True)
        if stale_bridge:
            srv_label = m_server or stale_bridge.get("server", "پیش‌فرض")
            return (
                0.0,
                f"اکانت متاتریدر {m_login} (عدم دریافت تیک زنده)",
                f"سرور: {srv_label} | ارتباط متاتریدر موقتاً قطع یا در حال همگام‌سازی مجدد است",
                False,
            )
        return (
            0.0,
            f"اکانت متاتریدر {m_login} (در حال همگام‌سازی...)",
            f"سرور: {m_server or 'پیش‌فرض'} | در انتظار دریافت اولین تیک از متاتریدر",
            False,
        )

    b_key = str(user_cfg.get("binance_api_key", "")).strip()
    b_secret = str(user_cfg.get("binance_secret_key", "")).strip()
    if b_key and b_secret:
        now_ts = time.time()
        cached_entry = _BINANCE_BALANCE_CACHE.get(b_key)
        if cached_entry and (now_ts - cached_entry[0]) < BINANCE_BALANCE_CACHE_TTL:
            return cached_entry[1]

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
            result = (real_equity, "بایننس فیوچرز (زنده)", f"صرافی متصل: بایننس | موجودی: {real_equity:.2f} USDT", True)
            _BINANCE_BALANCE_CACHE[b_key] = (now_ts, result)
            return result
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