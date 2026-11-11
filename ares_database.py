"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 5: MULTI-USER SQL DATABASE ENGINE
VERSION: 14.2 (MULTI-TENANT SUPPORT, PERSISTENT REAL TRADES, ZERO GHOST TRADES)
================================================================================
"""

import hashlib
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "ares_trading.db")


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
                    created_at DATETIME NOT NULL
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
                    opened_at DATETIME NOT NULL,
                    closed_at DATETIME
                );
            """)

            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN mt5_ticket INTEGER DEFAULT 0;")
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
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades(user_id, status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_ticket ON trades(mt5_ticket);")

    @staticmethod
    def _hash_pw(password: str) -> str:
        return hashlib.sha256(password.strip().encode()).hexdigest()

    def register_user(self, identifier: str, password: str) -> Optional[Dict[str, Any]]:
        clean_id = identifier.strip().lower()
        if not clean_id or len(password.strip()) < 4:
            return None
        user_id = f"usr_{hashlib.md5(clean_id.encode()).hexdigest()[:12]}"
        pw_hash = self._hash_pw(password)
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (user_id, identifier, password_hash, created_at) VALUES (?, ?, ?, ?);",
                    (user_id, clean_id, pw_hash, now),
                )
                conn.execute(
                    "INSERT INTO user_broker_configs (user_id, updated_at) VALUES (?, ?);",
                    (user_id, now),
                )
                return {"user_id": user_id, "identifier": clean_id}
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
            return dict(row) if row else None

    def get_user_by_identifier_or_login(self, identifier: str = "", mt5_login: str = "") -> Optional[Dict[str, Any]]:
        clean_id = str(identifier).strip().lower()
        clean_login = str(mt5_login).strip()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if clean_login:
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
                str(cfg.get("binance_api_key", existing.get("binance_api_key", ""))).strip(),
                b_secret,
                str(cfg.get("mt5_login", existing.get("mt5_login", ""))).strip(),
                mt5_pass,
                str(cfg.get("mt5_server", existing.get("mt5_server", ""))).strip(),
                existing.get("is_auto_trading", 0),
                now,
            ))

    def toggle_auto_trading(self, user_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_auto_trading FROM user_broker_configs WHERE user_id = ?;", (user_id,))
            row = cursor.fetchone()
            new_val = 1 if (not row or row[0] == 0) else 0
            cursor.execute("UPDATE user_broker_configs SET is_auto_trading = ? WHERE user_id = ?;", (new_val, user_id))
            return bool(new_val)

    def disconnect_broker(self, user_id: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE user_broker_configs 
                SET binance_api_key = '', binance_secret_key = '', mt5_login = '', mt5_pass = '', mt5_server = '', is_auto_trading = 0 
                WHERE user_id = ?;
            """, (user_id,))

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
            return [dict(r) for r in cursor.fetchall()]

    def clean_all_ghost_trades(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM trades 
                    WHERE trade_id LIKE 'POS_%' 
                       OR trade_id LIKE 'TEST%' 
                       OR trade_id LIKE 'MOCK%'
                       OR (market = 'FOREX_OR_INDICES' AND (mt5_ticket IS NULL OR mt5_ticket <= 0));
                """)
        except Exception:
            pass

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

                cursor.execute("SELECT trade_id FROM trades WHERE user_id = ? AND mt5_ticket = ?;", (user_id, ticket))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        UPDATE trades 
                        SET current_volume = ?, stop_loss = ?, tp1 = ?, realized_pnl = ?, status = 'OPEN'
                        WHERE trade_id = ?;
                    """, (vol, sl, tp, profit, row["trade_id"]))
                else:
                    trade_id = f"MT5_{ticket}"
                    cursor.execute("""
                        INSERT OR REPLACE INTO trades (
                            trade_id, user_id, mt5_ticket, symbol, market, side, entry_price,
                            initial_volume, current_volume, stop_loss, initial_stop_loss,
                            tp1, tp2, tp3, risk_amount_usd, realized_pnl, total_fees,
                            is_break_even, status, opened_at
                        ) VALUES (?, ?, ?, ?, 'FOREX_OR_INDICES', ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.0, ?, 0.0, 0, 'OPEN', ?);
                    """, (trade_id, user_id, ticket, symbol, side, entry_price, vol, vol, sl, sl, tp, tp, tp, profit, now))

            cursor.execute("SELECT trade_id, mt5_ticket FROM trades WHERE user_id = ? AND status = 'OPEN' AND mt5_ticket > 0;", (user_id,))
            for row in cursor.fetchall():
                if int(row["mt5_ticket"]) not in active_tickets:
                    cursor.execute("""
                        UPDATE trades SET status = 'CLOSED', closed_at = ?, exit_reason = 'MT5_CLOSED'
                        WHERE trade_id = ?;
                    """, (now, row["trade_id"]))

    def get_user_open_trades(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT trade_id, user_id, symbol, market, side, entry_price, stop_loss, initial_stop_loss,
                       initial_volume, current_volume, tp1, tp2, tp3, risk_amount_usd,
                       realized_pnl, total_fees, is_break_even, status, mt5_ticket, opened_at
                FROM trades 
                WHERE user_id = ? 
                  AND status = 'OPEN'
                  AND (mt5_ticket > 0 OR market = 'CRYPTO_FUTURES')
                  AND trade_id NOT LIKE 'POS_%'
                ORDER BY opened_at DESC;
            """, (user_id,))
            return [dict(r) for r in cursor.fetchall()]

    def get_all_open_trades(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trades 
                WHERE status = 'OPEN' 
                  AND (mt5_ticket > 0 OR market = 'CRYPTO_FUTURES')
                  AND trade_id NOT LIKE 'POS_%';
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
                    status, exit_reason, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                pos_data["open_time"],
                pos_data.get("close_time"),
            ))

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