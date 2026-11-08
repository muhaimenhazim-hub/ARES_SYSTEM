"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 5: LIGHTWEIGHT SQL DATABASE ENGINE (MySQL-Compatible Schema)
VERSION: 2.0 (STRICT ZERO MOCK DATA & REAL CLOSED TRADES PNL)
================================================================================
"""

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class AresDatabaseManager:
    """
    مدیر پایگاه داده بهینه و سبک سیستم ARES
    """

    def __init__(self, db_path: str = "ares_trading.db"):
        self.db_path = db_path
        self._initialize_database()
        self.clean_all_mock_data()  # پاکسازی قطعی تمام دیتای فیک و نمونه قدیمی

    def _get_connection(self) -> sqlite3.Connection:
        """برقراری اتصال امن با فعال‌سازی کش و حالت فوق‌سریع WAL"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _initialize_database(self):
        """ساخت خودکار جداول استاندارد در صورت عدم وجود"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # ۱. جدول اصلی معاملات (Trades Table)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id VARCHAR(64) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
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

            # ۲. جدول خروج‌های پله‌ای
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS partial_exits (
                    exit_id VARCHAR(64) PRIMARY KEY,
                    trade_id VARCHAR(64) NOT NULL,
                    target_name VARCHAR(10) NOT NULL,
                    exit_price REAL NOT NULL,
                    closed_volume REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    fee_paid REAL NOT NULL,
                    executed_at DATETIME NOT NULL,
                    FOREIGN KEY (trade_id) REFERENCES trades(trade_id)
                );
            """)

            # ۳. جدول ستاپ‌ها و فرصت‌ها
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS setups_log (
                    setup_id VARCHAR(64) PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    setup_name VARCHAR(50) NOT NULL,
                    direction VARCHAR(10) NOT NULL,
                    score REAL NOT NULL,
                    suggested_risk_pct REAL NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    rejection_reason TEXT,
                    created_at DATETIME NOT NULL
                );
            """)

            # ۴. جدول عملکرد روزانه
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_performance (
                    log_date DATE PRIMARY KEY,
                    ending_equity REAL NOT NULL,
                    daily_realized_pnl REAL NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    drawdown_pct REAL DEFAULT 0.0
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_setups_date ON setups_log(created_at);")

            conn.commit()

    def clean_all_mock_data(self):
        """حذف کامل رکوردهای آزمایشی، تستی و نمونه جهت تضمین دیتای واقعی"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM trades WHERE trade_id LIKE 'POS_TEST%' OR trade_id LIKE 'TEST%' OR trade_id LIKE 'MOCK%';")
                cursor.execute("DELETE FROM partial_exits WHERE trade_id LIKE 'POS_TEST%' OR trade_id LIKE 'TEST%' OR trade_id LIKE 'MOCK%';")
                cursor.execute("DELETE FROM daily_performance;")
                conn.commit()
        except Exception:
            pass

    def record_new_trade(self, pos_data: Dict[str, Any]):
        """ثبت پوزیشن تازه باز شده در جدول trades"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO trades (
                    trade_id, symbol, market, side, entry_price, initial_volume,
                    current_volume, stop_loss, initial_stop_loss, tp1, tp2, tp3,
                    risk_amount_usd, realized_pnl, total_fees, is_break_even,
                    status, exit_reason, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                pos_data["position_id"],
                pos_data["symbol"],
                pos_data["market"],
                pos_data["side"],
                pos_data["entry_price"],
                pos_data["initial_volume"],
                pos_data["current_volume"],
                pos_data["stop_loss"],
                pos_data["initial_stop_loss"],
                pos_data["targets"]["tp1"],
                pos_data["targets"]["tp2"],
                pos_data["targets"]["tp3"],
                pos_data["risk_amount_usd"],
                pos_data.get("realized_pnl", 0.0),
                pos_data.get("total_fees_paid", 0.0),
                1 if pos_data.get("is_break_even") else 0,
                pos_data.get("status", "OPEN"),
                pos_data.get("exit_reason"),
                pos_data["open_time"],
                pos_data.get("close_time"),
            ))
            conn.commit()

    def record_partial_exit(self, exit_record: Dict[str, Any], trade_id: str):
        """ثبت هر بار خروج پله‌ای در جدول اختصاصی"""
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
            conn.commit()

    def record_setup_evaluation(self, opp_data: Dict[str, Any]):
        """ثبت ستاپ کشف‌شده و نمره آن"""
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
            conn.commit()

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """گزارش‌گیری دقیق و واقعی فقط از معاملات واقعی (بدون دیتای فیک)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # تعداد معاملات واقعی (بدون معاملات تستی)
            cursor.execute("SELECT COUNT(*) FROM trades WHERE trade_id NOT LIKE 'POS_TEST%' AND trade_id NOT LIKE 'TEST%';")
            total_trades = cursor.fetchone()[0]

            # تعداد معاملات باز واقعی
            cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'OPEN' AND trade_id NOT LIKE 'POS_TEST%' AND trade_id NOT LIKE 'TEST%';")
            open_trades = cursor.fetchone()[0]

            # محاسبه سود فقط و فقط از معاملات واقعی بسته‌شده
            cursor.execute("""
                SELECT SUM(realized_pnl), SUM(total_fees) 
                FROM trades 
                WHERE status = 'CLOSED' AND trade_id NOT LIKE 'POS_TEST%' AND trade_id NOT LIKE 'TEST%';
            """)
            row = cursor.fetchone()
            total_pnl = row[0] if (row and row[0] is not None) else 0.0
            total_fees = row[1] if (row and row[1] is not None) else 0.0

            return {
                "total_trades_count": total_trades,
                "open_trades_count": open_trades,
                "net_realized_pnl_usd": round(total_pnl, 2),
                "total_fees_paid_usd": round(total_fees, 2),
            }