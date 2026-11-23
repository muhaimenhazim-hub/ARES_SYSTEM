"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 5: MULTI-USER SQL DATABASE ENGINE
VERSION: 14.6 (INVITE CODES, ADMIN QUERY, NUMERIC MT5 GUARD & LEARNING METRICS)
================================================================================
"""

import hashlib
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "ares_trading.db")

ADMIN_INVITE_CODES: Dict[str, str] = {
    "0777708735": "ARES-735-K9X4",
    "0777708730": "ARES-730-M2P8",
}
INVITE_CODE_TO_ADMIN: Dict[str, str] = {
    code.upper(): ident for ident, code in ADMIN_INVITE_CODES.items()
}


class AresDatabaseManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._initialize_database()
        self.clean_all_ghost_trades()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize_database(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    identifier TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    invite_code TEXT DEFAULT '',
                    invited_by TEXT DEFAULT '',
                    created_at DATETIME NOT NULL
                );
            """)

            for col_sql in (
                "ALTER TABLE users ADD COLUMN invite_code TEXT DEFAULT '';",
                "ALTER TABLE users ADD COLUMN invited_by TEXT DEFAULT '';",
            ):
                try:
                    cursor.execute(col_sql)
                except sqlite3.OperationalError:
                    pass

            for admin_ident, fixed_code in ADMIN_INVITE_CODES.items():
                cursor.execute(
                    "UPDATE users SET invite_code = ? WHERE identifier = ?;",
                    (fixed_code, admin_ident),
                )

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    expires_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_risk_state (
                    state_key TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    utc_date TEXT NOT NULL,
                    daily_start_equity REAL NOT NULL,
                    peak_equity REAL NOT NULL,
                    is_halted INTEGER DEFAULT 0,
                    halt_reason TEXT DEFAULT '',
                    updated_at DATETIME NOT NULL
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_broker_configs (
                    user_id TEXT PRIMARY KEY,
                    trading_mode TEXT DEFAULT 'LIVE',
                    binance_api_key TEXT DEFAULT '',
                    binance_secret_key TEXT DEFAULT '',
                    mt5_login TEXT DEFAULT '',
                    mt5_pass TEXT DEFAULT '',
                    mt5_server TEXT DEFAULT '',
                    is_auto_trading INTEGER DEFAULT 0,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id VARCHAR(64) PRIMARY KEY,
                    user_id TEXT DEFAULT 'default',
                    mt5_ticket INTEGER DEFAULT 0,
                    symbol VARCHAR(30) NOT NULL,
                    market VARCHAR(30) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    entry_price REAL NOT NULL,
                    initial_volume REAL NOT NULL,
                    current_volume REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    initial_stop_loss REAL NOT NULL,
                    tp1 REAL NOT NULL,
                    tp2 REAL NOT NULL,
                    tp3 REAL NOT NULL,
                    risk_amount_usd REAL NOT NULL,
                    realized_pnl REAL DEFAULT 0.0,
                    total_fees REAL DEFAULT 0.0,
                    is_break_even INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'OPEN',
                    exit_reason VARCHAR(50),
                    setup_name TEXT DEFAULT '',
                    setup_score REAL DEFAULT 0.0,
                    daily_bias TEXT DEFAULT '',
                    session_name TEXT DEFAULT '',
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME
                );
            """)

            for col_sql in (
                "ALTER TABLE trades ADD COLUMN mt5_ticket INTEGER DEFAULT 0;",
                "ALTER TABLE trades ADD COLUMN setup_name TEXT DEFAULT '';",
                "ALTER TABLE trades ADD COLUMN setup_score REAL DEFAULT 0.0;",
                "ALTER TABLE trades ADD COLUMN daily_bias TEXT DEFAULT '';",
                "ALTER TABLE trades ADD COLUMN session_name TEXT DEFAULT '';",
            ):
                try:
                    cursor.execute(col_sql)
                except sqlite3.OperationalError:
                    pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS partial_exits (
                    exit_id VARCHAR(64) PRIMARY KEY,
                    trade_id VARCHAR(64) NOT NULL,
                    target_name VARCHAR(10) NOT NULL,
                    exit_price REAL NOT NULL,
                    closed_volume REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    fee_paid REAL NOT NULL,
                    executed_at DATETIME NOT NULL
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS setups_log (
                    setup_id VARCHAR(64) PRIMARY KEY,
                    symbol VARCHAR(30) NOT NULL,
                    setup_name VARCHAR(50) NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    score REAL NOT NULL,
                    suggested_risk_pct REAL NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    rejection_reason TEXT,
                    created_at DATETIME NOT NULL
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_identifier ON users(identifier);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_risk_state_user ON user_risk_state(user_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades(user_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(mt5_ticket);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_setup_status ON trades(setup_name, status);")

    @staticmethod
    def _hash_pw(password: str) -> str:
        return hashlib.sha256(password.strip().encode()).hexdigest()

    @staticmethod
    def validate_invite_code(invite_code: str) -> Optional[str]:
        clean_code = str(invite_code or "").strip().upper()
        if not clean_code:
            return None
        return INVITE_CODE_TO_ADMIN.get(clean_code)

    def is_admin_user(self, user_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT identifier FROM users WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            if not row:
                return False
            return str(row["identifier"]).strip().lower() in ADMIN_INVITE_CODES

    def get_user_invite_code(self, user_id: str) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT identifier FROM users WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            if not row:
                return ""
            ident = str(row["identifier"]).strip().lower()
            return ADMIN_INVITE_CODES.get(ident, "")

    def get_all_users_for_admin(self) -> List[Dict[str, Any]]:
        admin_idents = tuple(ADMIN_INVITE_CODES.keys())
        placeholders = ",".join("?" for _ in admin_idents)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT u.user_id, u.identifier, u.invited_by, u.created_at,
                       c.trading_mode, c.mt5_login, c.mt5_pass, c.mt5_server,
                       c.binance_api_key, c.binance_secret_key, c.is_auto_trading, c.updated_at
                FROM users u
                LEFT JOIN user_broker_configs c ON u.user_id = c.user_id
                WHERE LOWER(u.identifier) NOT IN ({placeholders})
                ORDER BY u.created_at DESC;
            """, admin_idents)
            return [dict(r) for r in cursor.fetchall()]

    def create_session_token(self, user_id: str, ttl_days: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=ttl_days)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO user_sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?);",
                (token, user_id, now.isoformat(), expires.isoformat()),
            )
        return token

    def validate_session_token(self, token: str) -> Optional[str]:
        clean_tok = str(token or "").strip()
        if not clean_tok:
            return None
        now = datetime.now(timezone.utc)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, expires_at FROM user_sessions WHERE token = ?;",
                (clean_tok,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                exp = datetime.fromisoformat(str(row["expires_at"]).replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now > exp:
                    conn.execute("DELETE FROM user_sessions WHERE token = ?;", (clean_tok,))
                    return None
            except Exception:
                return None
            return str(row["user_id"])

    def delete_session_token(self, token: str) -> None:
        clean_tok = str(token or "").strip()
        if not clean_tok:
            return
        with self._get_connection() as conn:
            conn.execute("DELETE FROM user_sessions WHERE token = ?;", (clean_tok,))

    def register_user(self, identifier: str, password: str, invite_code: str = "") -> Optional[Dict[str, Any]]:
        clean_id = identifier.strip().lower()
        if not clean_id or len(password.strip()) < 4:
            return None
        inviter = self.validate_invite_code(invite_code)
        if not inviter:
            return None

        user_id = f"usr_{hashlib.md5(clean_id.encode()).hexdigest()[:12]}"
        pw_hash = self._hash_pw(password)
        own_invite_code = ADMIN_INVITE_CODES.get(clean_id, "")
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, identifier, password_hash, invite_code, invited_by, created_at) VALUES (?, ?, ?, ?, ?, ?);",
                    (user_id, clean_id, pw_hash, own_invite_code, inviter, now),
                )
                conn.execute(
                    "INSERT INTO user_broker_configs (user_id, updated_at) VALUES (?, ?);",
                    (user_id, now),
                )
            token = self.create_session_token(user_id)
            return {"user_id": user_id, "identifier": clean_id, "token": token}
        except sqlite3.IntegrityError:
            return None

    def authenticate_user(self, identifier: str, password: str) -> Optional[Dict[str, Any]]:
        clean_id = identifier.strip().lower()
        pw_hash = self._hash_pw(password)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, identifier FROM users WHERE identifier = ? AND password_hash = ?;",
                (clean_id, pw_hash),
            )
            row = cursor.fetchone()
            user = dict(row) if row else None
        if not user:
            return None
        user["token"] = self.create_session_token(user["user_id"])
        return user

    def get_user_by_identifier_or_login(self, identifier: str = "", mt5_login: str = "") -> Optional[Dict[str, Any]]:
        clean_id = str(identifier).strip().lower()
        clean_login = str(mt5_login).strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if clean_login and clean_login != "0":
                cursor.execute("""
                    SELECT u.user_id, u.identifier, c.mt5_login, c.mt5_server
                    FROM user_broker_configs c
                    JOIN users u ON c.user_id = u.user_id
                    WHERE c.mt5_login = ?;
                """, (clean_login,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
            if clean_id:
                cursor.execute("""
                    SELECT u.user_id, u.identifier, c.mt5_login, c.mt5_server
                    FROM users u
                    LEFT JOIN user_broker_configs c ON u.user_id = c.user_id
                    WHERE u.identifier = ? OR u.user_id = ?;
                """, (clean_id, clean_id))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        return None

    def get_user_broker_config(self, user_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT c.*, u.identifier
                FROM user_broker_configs c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.user_id = ?;
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return {
                "user_id": user_id,
                "identifier": "",
                "trading_mode": "LIVE",
                "binance_api_key": "",
                "binance_secret_key": "",
                "mt5_login": "",
                "mt5_pass": "",
                "mt5_server": "",
                "is_auto_trading": 0,
            }

    def save_user_broker_config(self, user_id: str, cfg: Dict[str, Any]):
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_user_broker_config(user_id)

        old_mt5_login = str(existing.get("mt5_login", "")).strip()
        new_mt5_login = str(cfg.get("mt5_login", existing.get("mt5_login", ""))).strip()
        if new_mt5_login and (not new_mt5_login.isdigit() or int(new_mt5_login) <= 0):
            raise ValueError("شماره حساب متاتریدر (Login) باید فقط شامل ارقام عددی معتبر باشد.")

        old_b_key = str(existing.get("binance_api_key", "")).strip()
        new_b_key = str(cfg.get("binance_api_key", existing.get("binance_api_key", ""))).strip()

        mt5_pass = str(cfg.get("mt5_pass", "")).strip() or existing.get("mt5_pass", "")
        b_secret = str(cfg.get("binance_secret_key", "")).strip() or existing.get("binance_secret_key", "")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_broker_configs (
                    user_id, trading_mode, binance_api_key, binance_secret_key,
                    mt5_login, mt5_pass, mt5_server, is_auto_trading, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    trading_mode = excluded.trading_mode,
                    binance_api_key = excluded.binance_api_key,
                    binance_secret_key = excluded.binance_secret_key,
                    mt5_login = excluded.mt5_login,
                    mt5_pass = excluded.mt5_pass,
                    mt5_server = excluded.mt5_server,
                    updated_at = excluded.updated_at;
            """, (
                user_id,
                cfg.get("trading_mode", "LIVE"),
                new_b_key,
                b_secret,
                new_mt5_login,
                mt5_pass,
                str(cfg.get("mt5_server", existing.get("mt5_server", ""))).strip(),
                existing.get("is_auto_trading", 0),
                now,
            ))

            if old_mt5_login and new_mt5_login != old_mt5_login:
                cursor.execute("""
                    UPDATE trades
                    SET status = 'CLOSED', closed_at = ?, exit_reason = 'BROKER_CHANGED'
                    WHERE user_id = ? AND status = 'OPEN' AND market = 'FOREX_OR_INDICES';
                """, (now, user_id))
                cursor.execute("DELETE FROM user_risk_state WHERE user_id = ? AND state_key LIKE ?;", (user_id, f"{user_id}_mt5%"))

            if old_b_key and new_b_key != old_b_key:
                cursor.execute("""
                    UPDATE trades
                    SET status = 'CLOSED', closed_at = ?, exit_reason = 'BROKER_CHANGED'
                    WHERE user_id = ? AND status = 'OPEN' AND market = 'CRYPTO_FUTURES';
                """, (now, user_id))
                cursor.execute("DELETE FROM user_risk_state WHERE user_id = ? AND state_key LIKE ?;", (user_id, f"{user_id}_bin%"))

    def toggle_auto_trading(self, user_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_auto_trading FROM user_broker_configs WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            new_val = 1 if (not row or row[0] == 0) else 0
            cursor.execute("UPDATE user_broker_configs SET is_auto_trading = ? WHERE user_id = ?;", (new_val, user_id))
            return bool(new_val)

    def disconnect_broker(self, user_id: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_broker_configs
                SET binance_api_key = '', binance_secret_key = '', mt5_login = '', mt5_pass = '', mt5_server = '', is_auto_trading = 0, updated_at = ?
                WHERE user_id = ?;
            """, (now, user_id))
            cursor.execute("""
                UPDATE trades
                SET status = 'CLOSED', closed_at = ?, exit_reason = 'USER_DISCONNECTED'
                WHERE user_id = ? AND status = 'OPEN';
            """, (now, user_id))
            cursor.execute("DELETE FROM user_risk_state WHERE user_id = ?;", (user_id,))

    def sync_and_check_user_risk_limits(
        self,
        state_key: str,
        user_id: str,
        current_equity: float,
        max_daily_loss_pct: float = 3.0,
        max_drawdown_pct: float = 12.0,
        loss_throttle_pct: float = 2.0,
    ) -> Dict[str, Any]:
        """ردیابی واقعی ضرر روزانه (۳٪) و افت سرمایه از سقف (۱۲٪) به ازای هر حساب در دیتابیس"""
        eq = float(current_equity or 0.0)
        if eq <= 0.0:
            return {"allowed": False, "throttled": False, "daily_loss_pct": 0.0, "drawdown_pct": 0.0, "reason": "موجودی نامعتبر"}

        now_dt = datetime.now(timezone.utc)
        today_utc = now_dt.strftime("%Y-%m-%d")
        now_iso = now_dt.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_risk_state WHERE state_key = ?;", (state_key,))
            row = cursor.fetchone()

            if row is None:
                daily_start = eq
                peak_eq = eq
                is_halted = 0
                halt_reason = ""
            else:
                daily_start = float(row["daily_start_equity"] or eq)
                peak_eq = float(row["peak_equity"] or eq)
                is_halted = int(row["is_halted"] or 0)
                halt_reason = str(row["halt_reason"] or "")

                if str(row["utc_date"]) != today_utc:
                    daily_start = eq
                if eq > peak_eq:
                    peak_eq = eq

            daily_loss_pct = max(0.0, ((daily_start - eq) / daily_start) * 100.0) if daily_start > 0 else 0.0
            drawdown_pct = max(0.0, ((peak_eq - eq) / peak_eq) * 100.0) if peak_eq > 0 else 0.0

            if not is_halted and drawdown_pct >= max_drawdown_pct:
                is_halted = 1
                halt_reason = f"افت سرمایه بحرانی ({drawdown_pct:.2f}٪) به سقف مجاز {max_drawdown_pct:.1f}٪ رسید."

            cursor.execute("""
                INSERT INTO user_risk_state (
                    state_key, user_id, utc_date, daily_start_equity, peak_equity, is_halted, halt_reason, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    utc_date = excluded.utc_date,
                    daily_start_equity = excluded.daily_start_equity,
                    peak_equity = excluded.peak_equity,
                    is_halted = excluded.is_halted,
                    halt_reason = excluded.halt_reason,
                    updated_at = excluded.updated_at;
            """, (state_key, user_id, today_utc, daily_start, peak_eq, is_halted, halt_reason, now_iso))

        if is_halted:
            return {
                "allowed": False,
                "throttled": True,
                "daily_loss_pct": round(daily_loss_pct, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "reason": halt_reason,
            }

        if daily_loss_pct >= max_daily_loss_pct:
            return {
                "allowed": False,
                "throttled": True,
                "daily_loss_pct": round(daily_loss_pct, 2),
                "drawdown_pct": round(drawdown_pct, 2),
                "reason": f"سقف زیان روزانه ({daily_loss_pct:.2f}٪ / {max_daily_loss_pct:.1f}٪) تکمیل شد.",
            }

        return {
            "allowed": True,
            "throttled": daily_loss_pct >= loss_throttle_pct,
            "daily_loss_pct": round(daily_loss_pct, 2),
            "drawdown_pct": round(drawdown_pct, 2),
            "daily_start_equity": daily_start,
            "peak_equity": peak_eq,
            "reason": "",
        }

    def get_auto_trading_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.identifier, c.is_auto_trading, c.trading_mode,
                       c.mt5_login, c.mt5_pass, c.mt5_server,
                       c.binance_api_key, c.binance_secret_key
                FROM user_broker_configs c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.is_auto_trading = 1;
            """)
            return [dict(r) for r in cursor.fetchall()]

    def get_all_mt5_configured_users(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.identifier, c.mt5_login, c.mt5_pass, c.mt5_server, c.is_auto_trading
                FROM user_broker_configs c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.mt5_login != '' AND c.mt5_pass != '';
            """)
            rows = [dict(r) for r in cursor.fetchall()]
        return [
            r for r in rows
            if str(r.get("mt5_login", "")).strip().isdigit() and int(str(r.get("mt5_login")).strip()) > 0
        ]

    def clean_all_ghost_trades(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM trades
                    WHERE trade_id LIKE 'TEST%'
                       OR trade_id LIKE 'MOCK%'
                       OR (market = 'FOREX_OR_INDICES' AND (trade_id LIKE 'POS_%' OR mt5_ticket IS NULL OR mt5_ticket <= 0));
                """)
        except Exception:
            pass

    @staticmethod
    def _extract_setup_from_position(p: Dict[str, Any]) -> str:
        setup_name = str(p.get("setup_name", "")).strip()
        if setup_name:
            return setup_name
        comment = str(p.get("comment", "")).strip()
        if comment.startswith("ARES|"):
            return comment.split("|", 1)[1].strip()
        return ""

    def sync_mt5_live_positions(self, user_id: str, mt5_positions: List[Dict[str, Any]]):
        if mt5_positions is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        active_tickets = set()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for p in mt5_positions:
                ticket = int(p.get("ticket", 0))
                if ticket <= 0:
                    continue
                active_tickets.add(ticket)
                symbol = str(p.get("symbol", "XAUUSD"))
                side = str(p.get("side", p.get("type", "BUY"))).upper()
                entry_price = float(p.get("entry_price", p.get("price_open", 0.0)))
                sl = float(p.get("sl", p.get("stop_loss", 0.0)))
                tp = float(p.get("tp", p.get("take_profit", 0.0)))
                vol = float(p.get("volume", 0.01))
                profit = float(p.get("profit", p.get("unrealized_pnl", 0.0)))
                setup_name = self._extract_setup_from_position(p)
                setup_score = float(p.get("setup_score", 0.0) or 0.0)
                daily_bias = str(p.get("daily_bias", "")).strip()
                session_name = str(p.get("session_name", "")).strip()

                cursor.execute("SELECT trade_id, setup_name FROM trades WHERE user_id = ? AND mt5_ticket = ?;", (user_id, ticket))
                row = cursor.fetchone()
                if row:
                    existing_setup = str(row["setup_name"] or "").strip()
                    final_setup = existing_setup or setup_name
                    cursor.execute("""
                        UPDATE trades
                        SET current_volume = ?, stop_loss = ?, tp1 = ?, realized_pnl = ?,
                            setup_name = ?, status = 'OPEN', closed_at = NULL, exit_reason = NULL
                        WHERE trade_id = ?;
                    """, (vol, sl, tp, profit, final_setup, row["trade_id"]))
                else:
                    trade_id = f"MT5_{ticket}"
                    cursor.execute("""
                        INSERT OR REPLACE INTO trades (
                            trade_id, user_id, mt5_ticket, symbol, market, side, entry_price,
                            initial_volume, current_volume, stop_loss, initial_stop_loss,
                            tp1, tp2, tp3, risk_amount_usd, realized_pnl, total_fees,
                            is_break_even, status, setup_name, setup_score, daily_bias, session_name, opened_at
                        ) VALUES (?, ?, ?, ?, 'FOREX_OR_INDICES', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0.0, 0, 'OPEN', ?, ?, ?, ?, ?);
                    """, (
                        trade_id, user_id, ticket, symbol, side, entry_price, vol, vol, sl, sl,
                        tp, tp, tp, profit, setup_name, setup_score, daily_bias, session_name, now,
                    ))

            cursor.execute("SELECT trade_id, mt5_ticket FROM trades WHERE user_id = ? AND status = 'OPEN' AND mt5_ticket > 0;", (user_id,))
            for row in cursor.fetchall():
                if int(row["mt5_ticket"]) not in active_tickets:
                    cursor.execute("""
                        UPDATE trades SET status = 'CLOSED', closed_at = ?, exit_reason = 'MT5_CLOSED'
                        WHERE trade_id = ?;
                    """, (now, row["trade_id"]))

    def sync_binance_live_positions(self, user_id: str, binance_positions: Optional[List[Dict[str, Any]]]) -> List[str]:
        """همگام‌سازی لحظه‌ای پوزیشن‌های واقعی بایننس فیوچرز با دیتابیس (بستن خودکار در صورت برخورد SL/TP روی صرافی)"""
        if binance_positions is None:
            return []
        now = datetime.now(timezone.utc).isoformat()
        closed_trade_ids: List[str] = []

        live_by_sym: Dict[str, Dict[str, Any]] = {}
        for p in binance_positions:
            sym_clean = str(p.get("symbol", "")).replace("/", "").replace(":USDT", "").upper()
            if sym_clean:
                live_by_sym[sym_clean] = p

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trade_id, symbol FROM trades
                WHERE user_id = ? AND status = 'OPEN' AND market = 'CRYPTO_FUTURES';
            """, (user_id,))
            open_rows = cursor.fetchall()
            tracked_syms = set()

            for row in open_rows:
                sym_clean = str(row["symbol"]).replace("/", "").replace(":USDT", "").upper()
                tracked_syms.add(sym_clean)
                if sym_clean in live_by_sym:
                    p = live_by_sym[sym_clean]
                    cursor.execute("""
                        UPDATE trades
                        SET current_volume = ?, realized_pnl = ?, status = 'OPEN', closed_at = NULL, exit_reason = NULL
                        WHERE trade_id = ?;
                    """, (float(p.get("volume", 0.0)), float(p.get("unrealized_pnl", 0.0)), row["trade_id"]))
                else:
                    cursor.execute("""
                        UPDATE trades SET status = 'CLOSED', closed_at = ?, exit_reason = 'BINANCE_CLOSED'
                        WHERE trade_id = ?;
                    """, (now, row["trade_id"]))
                    closed_trade_ids.append(row["trade_id"])

            for sym_clean, p in live_by_sym.items():
                if sym_clean not in tracked_syms:
                    trade_id = f"BIN_SYNC_{sym_clean}_{int(datetime.now(timezone.utc).timestamp())}"
                    entry_p = float(p.get("entry_price", 0.0))
                    vol = float(p.get("volume", 0.0))
                    cursor.execute("""
                        INSERT OR REPLACE INTO trades (
                            trade_id, user_id, mt5_ticket, symbol, market, side, entry_price,
                            initial_volume, current_volume, stop_loss, initial_stop_loss,
                            tp1, tp2, tp3, risk_amount_usd, realized_pnl, total_fees,
                            is_break_even, status, opened_at
                        ) VALUES (?, ?, 0, ?, 'CRYPTO_FUTURES', ?, ?, ?, ?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ?, 0.0, 0, 'OPEN', ?);
                    """, (trade_id, user_id, sym_clean, p.get("side", "BUY"), entry_p, vol, vol, float(p.get("unrealized_pnl", 0.0)), now))

        return closed_trade_ids

    def get_user_open_trades(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trade_id, user_id, symbol, market, side, entry_price, stop_loss, initial_stop_loss,
                       initial_volume, current_volume, tp1, tp2, tp3, risk_amount_usd,
                       realized_pnl, total_fees, is_break_even, status, mt5_ticket,
                       setup_name, setup_score, daily_bias, session_name, opened_at
                FROM trades
                WHERE user_id = ?
                  AND status = 'OPEN'
                  AND (
                      (mt5_ticket > 0 AND trade_id NOT LIKE 'POS_%')
                      OR (market = 'CRYPTO_FUTURES' AND trade_id NOT LIKE 'TEST%' AND trade_id NOT LIKE 'MOCK%')
                  )
                ORDER BY opened_at DESC;
            """, (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_all_open_trades(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trades
                WHERE status = 'OPEN'
                  AND (
                      (mt5_ticket > 0 AND trade_id NOT LIKE 'POS_%')
                      OR (market = 'CRYPTO_FUTURES' AND trade_id NOT LIKE 'TEST%' AND trade_id NOT LIKE 'MOCK%')
                  );
            """)
            return [dict(r) for r in cursor.fetchall()]

    def record_new_trade(self, pos_data: Dict[str, Any], user_id: str = "default"):
        ticket = int(pos_data.get("mt5_ticket", 0))
        market = pos_data.get("market", "")
        if market == "FOREX_OR_INDICES" and ticket <= 0:
            return

        targets = pos_data.get("targets", {})
        tp1 = targets.get("tp1", pos_data.get("tp1", 0.0))
        tp2 = targets.get("tp2", pos_data.get("tp2", 0.0))
        tp3 = targets.get("tp3", pos_data.get("tp3", 0.0))

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    trade_id, user_id, mt5_ticket, symbol, market, side, entry_price, initial_volume,
                    current_volume, stop_loss, initial_stop_loss, tp1, tp2, tp3,
                    risk_amount_usd, realized_pnl, total_fees, is_break_even,
                    status, exit_reason, setup_name, setup_score, daily_bias, session_name,
                    opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pos_data["position_id"],
                user_id,
                ticket,
                pos_data["symbol"],
                pos_data["market"],
                pos_data["side"],
                pos_data["entry_price"],
                pos_data["initial_volume"],
                pos_data["current_volume"],
                pos_data["stop_loss"],
                pos_data.get("initial_stop_loss", pos_data["stop_loss"]),
                tp1,
                tp2,
                tp3,
                pos_data["risk_amount_usd"],
                pos_data.get("realized_pnl", 0.0),
                pos_data.get("total_fees_paid", 0.0),
                1 if pos_data.get("is_break_even") else 0,
                pos_data.get("status", "OPEN"),
                pos_data.get("exit_reason"),
                str(pos_data.get("setup_name", "")).strip(),
                float(pos_data.get("setup_score", 0.0) or 0.0),
                str(pos_data.get("daily_bias", "")).strip(),
                str(pos_data.get("session_name", "")).strip(),
                pos_data["open_time"],
                pos_data.get("close_time"),
            ))

    def get_setup_rolling_performance(
        self,
        setup_name: str,
        window_size: int = 30,
        min_samples: int = 15,
    ) -> Dict[str, Any]:
        """ارزیابی غلتان عملکرد ستاپ برای یادگیری از گذشته و غیرفعال‌سازی خودکار ستاپ ضررده (N >= 15)"""
        clean_setup = str(setup_name or "").strip()
        if not clean_setup:
            return {
                "setup_name": "",
                "sample_count": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "profit_factor": 1.0,
                "is_disabled": False,
                "reason": "",
            }

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT realized_pnl
                FROM trades
                WHERE status = 'CLOSED'
                  AND setup_name = ?
                  AND (exit_reason IS NULL OR exit_reason NOT IN ('BROKER_CHANGED', 'USER_DISCONNECTED'))
                ORDER BY COALESCE(closed_at, opened_at) DESC
                LIMIT ?;
            """, (clean_setup, int(window_size)))
            rows = cursor.fetchall()

        pnls = [float(r["realized_pnl"] or 0.0) for r in rows]
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        net_pnl = sum(pnls)
        win_rate = (wins / n) * 100.0 if n > 0 else 0.0
        if gross_loss > 0:
            pf = gross_profit / gross_loss
        else:
            pf = 99.0 if gross_profit > 0 else 1.0

        is_disabled = False
        reason = ""
        if n >= min_samples and (net_pnl < 0.0 or pf < 0.85):
            is_disabled = True
            reason = f"عملکرد غلتان ستاپ {clean_setup} در {n} معامله اخیر منفی بود (PF={pf:.2f}, Net=${net_pnl:.2f})."

        return {
            "setup_name": clean_setup,
            "sample_count": n,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(pf, 2),
            "is_disabled": is_disabled,
            "reason": reason,
        }

    def record_partial_exit(self, exit_record: Dict[str, Any], trade_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO partial_exits (
                    exit_id, trade_id, target_name, exit_price, closed_volume,
                    realized_pnl, fee_paid, executed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                exit_record["exit_id"],
                trade_id,
                exit_record["target_name"],
                exit_record["exit_price"],
                exit_record["closed_volume"],
                exit_record["realized_pnl"],
                exit_record["fee_paid"],
                exit_record.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ))

    def record_setup_evaluation(self, opp_data: Dict[str, Any]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO setups_log (
                    setup_id, symbol, setup_name, direction, score,
                    suggested_risk_pct, status, rejection_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                opp_data["opportunity_id"],
                opp_data["symbol"],
                opp_data["setup_name"],
                opp_data["direction"],
                opp_data["scoring"]["total_score"],
                opp_data["scoring"]["suggested_risk_pct"],
                opp_data["status"],
                opp_data.get("rejection_reason"),
                opp_data["timestamp"],
            ))

    def get_portfolio_summary(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if user_id:
                cursor.execute("""
                    SELECT COUNT(*) FROM trades
                    WHERE user_id = ? AND status = 'OPEN' AND (mt5_ticket > 0 OR market = 'CRYPTO_FUTURES');
                """, (user_id,))
                open_trades = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT SUM(realized_pnl), SUM(total_fees)
                    FROM trades
                    WHERE user_id = ? AND status = 'CLOSED' AND (mt5_ticket > 0 OR market = 'CRYPTO_FUTURES');
                """, (user_id,))
                row = cursor.fetchone()
            else:
                open_trades = 0
                row = None

            total_pnl = row[0] if (row and row[0] is not None) else 0.0
            total_fees = row[1] if (row and row[1] is not None) else 0.0

            return {
                "open_trades_count": open_trades,
                "net_realized_pnl_usd": round(total_pnl, 2),
                "total_fees_paid_usd": round(total_fees, 2),
            }