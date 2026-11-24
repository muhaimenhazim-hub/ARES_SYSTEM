"""
================================================================================
ARES AI TRADING SYSTEM
MASTER REAL-TIME ENGINE + MULTI-USER INTEGRATION (main.py)
VERSION: 14.8 (FVG-ONLY, 2.0R STAGED EXITS, ROLLING LEARNING & BIAS PROTECTION)
================================================================================
"""

from datetime import datetime, timezone
import sys
import time
from typing import Any, Dict, List, Optional
import pandas as pd

import account_config
from ares_01_crt_strategy_engine import CRTStrategyEngine
from ares_02_smc_ict_strategy_engine import SMCICTStrategyEngine
from ares_03_master_setup_engine import MasterSetupEngine
from ares_04_trade_position_management_engine import (
    ExecutionMode,
    TradePositionManagementEngine,
)
from ares_05_risk_management_portfolio_control_engine import (
    ContractSpecs,
    RiskManagementPortfolioEngine,
)
from ares_database import AresDatabaseManager
from ares_news_filter import EconomicNewsFilter
from market_data_connector import AresUnifiedDataService


class AresMasterSystem:
    SYMBOLS_SPECS = {
        # فارکس، انس طلا و شاخص‌ها (مخصوص متاتریدر ۵ با سقف ایمن متناسب با حجم حساب)
        "XAUUSD": ContractSpecs("XAUUSD", min_volume=0.01, max_volume=5.0, volume_step=0.01, tick_size=0.01, contract_size=100.0, min_notional_usd=1.0, leverage=100.0),
        "EURUSD": ContractSpecs("EURUSD", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.00001, contract_size=100000.0, min_notional_usd=1.0, leverage=100.0),
        "NASDAQ 100": ContractSpecs("NASDAQ 100", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        "S&P 500": ContractSpecs("S&P 500", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        # کریپتو فیوچرز (فقط در صورت اتصال API بایننس)
        "BTCUSDT": ContractSpecs("BTCUSDT", min_volume=0.001, max_volume=5.0, volume_step=0.001, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ETHUSDT": ContractSpecs("ETHUSDT", min_volume=0.01, max_volume=20.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "BNBUSDT": ContractSpecs("BNBUSDT", min_volume=0.01, max_volume=50.0, volume_step=0.01, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ADAUSDT": ContractSpecs("ADAUSDT", min_volume=1.0, max_volume=5000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "XRPUSDT": ContractSpecs("XRPUSDT", min_volume=1.0, max_volume=5000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "1000PEPEUSDT": ContractSpecs("1000PEPEUSDT", min_volume=100.0, max_volume=500000.0, volume_step=100.0, tick_size=0.000001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
    }

    def __init__(self):
        print("=" * 80)
        print("🏛 راه‌اندازی ربات هوشمند ARES (نسخه ۱۴.۸ - ستاپ FVG، خروج پله‌ای 2.0R، یادگیری غلتان و بایاس D1/H4)")
        print("=" * 80)

        self.db = AresDatabaseManager()
        self.data_service = AresUnifiedDataService()
        self.news_filter = EconomicNewsFilter(blackout_window_minutes=30)
        self.crt_engine = CRTStrategyEngine()
        self.smc_engine = SMCICTStrategyEngine()
        self.setup_engine = MasterSetupEngine(min_rr_ratio=1.5)

        self.user_risk_engines: Dict[str, RiskManagementPortfolioEngine] = {}
        self.trade_engine = TradePositionManagementEngine(mode=ExecutionMode.LIVE)
        self.last_scan_time: float = 0.0
        self.last_binance_sync_time: float = 0.0
        self.last_bias_protect_check_time: float = 0.0

        self.pending_trade_locks: Dict[str, float] = {}
        self.symbol_last_candle_time: Dict[str, str] = {}
        self._risk_alert_last_ts: Dict[str, float] = {}
        self.recent_order_metadata: Dict[str, Dict[str, Any]] = {}
        self._bias_protect_last_ts: Dict[int, float] = {}
        self.gold_fast_pending: Optional[Dict[str, Any]] = None
        self.gold_used_refs: Dict[str, float] = {}

        self._restore_open_positions_from_db()

    @staticmethod
    def is_forex_session_open() -> bool:
        """فیلتر ۲۲ ساعته معاملاتی: توقف در ۲ ساعت رول‌اور شبانه (21:00 تا 23:00 UTC) و تعطیلات پایان هفته"""
        utc_now = datetime.now(timezone.utc)
        if utc_now.weekday() in (5, 6):
            return False
        if 21 <= utc_now.hour < 23:
            return False
        return True

    @staticmethod
    def get_current_session_name() -> str:
        hour = datetime.now(timezone.utc).hour
        if 0 <= hour < 7:
            return "ASIAN"
        if 7 <= hour < 12:
            return "LONDON"
        if 12 <= hour < 16:
            return "LDN_NY_OVERLAP"
        if 16 <= hour < 21:
            return "NEW_YORK"
        if 21 <= hour < 23:
            return "ROLLOVER"
        return "LATE_ASIA"

    def _log_risk_alert_throttled(self, key: str, message: str, cooldown: float = 300.0):
        now = time.time()
        if now - self._risk_alert_last_ts.get(key, 0.0) >= cooldown:
            self._risk_alert_last_ts[key] = now
            print(message, flush=True)

    def _get_user_risk_engine(self, user_id: str, current_equity: float) -> RiskManagementPortfolioEngine:
        """ایجاد یا بازیابی موتور ریسک کاملاً ایزوله برای هر کاربر جهت جلوگیری از تداخل سرمایه کاربران"""
        eng = self.user_risk_engines.get(user_id)
        if eng is None:
            eng = RiskManagementPortfolioEngine(initial_capital=max(1.0, float(current_equity)))
            self.user_risk_engines[user_id] = eng
        else:
            eng.current_capital = float(current_equity)
        return eng

    def _restore_open_positions_from_db(self):
        try:
            open_rows = self.db.get_all_open_trades()
            for row in open_rows:
                self.trade_engine.restore_position_from_db(row)
            if open_rows:
                print(f"✅ تعداد {len(open_rows)} پوزیشن واقعی از دیتابیس بازیابی شد.")
            else:
                print("✨ دیتابیس کاملاً تمیز است؛ هیچ پوزیشن شبحی وجود ندارد.")
        except Exception as e:
            print(f"⚠️ خطا در بازیابی اولیه: {e}")

    def _get_user_routing_keys(self, user_id: str) -> List[str]:
        cfg = self.db.get_user_broker_config(user_id)
        keys = [
            user_id,
            str(cfg.get("identifier", "")),
            str(cfg.get("mt5_login", "")),
        ]
        return [k.strip().lower() for k in keys if k and str(k).strip()]

    @staticmethod
    def _match_canonical_symbol(broker_sym: str) -> Optional[str]:
        bs = str(broker_sym or "").strip()
        if not bs:
            return None
        for canon_sym, aliases in account_config.BROKER_SYMBOL_ALIASES.items():
            for alias in aliases:
                if account_config._symbol_matches_alias(bs, alias, allow_prefix=True):
                    return canon_sym
        return None

    def _enrich_mt5_trade_metadata(self):
        """تکمیل خودکار متادیتای یادگیری (امتیاز ستاپ، بایاس روزانه و سشن) پس از ثبت تیکت متاتریدر در دیتابیس"""
        now_ts = time.time()
        for k in [key for key, val in self.recent_order_metadata.items() if (now_ts - float(val.get("ts", 0.0))) > 900.0]:
            del self.recent_order_metadata[k]

        if not self.recent_order_metadata:
            return

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT trade_id, user_id, symbol, setup_name, setup_score, daily_bias, session_name
                    FROM trades
                    WHERE status = 'OPEN'
                      AND mt5_ticket > 0
                      AND (daily_bias = '' OR setup_score = 0 OR session_name = '');
                """)
                rows = cursor.fetchall()
                for row in rows:
                    canon_sym = self._match_canonical_symbol(row["symbol"])
                    if not canon_sym:
                        continue
                    clean_sym = canon_sym.replace(" ", "").rstrip(".")
                    meta = self.recent_order_metadata.get(f"{row['user_id']}_{clean_sym}")
                    if not meta:
                        continue
                    final_setup = str(row["setup_name"] or "").strip() or meta.get("setup_name", "")
                    cursor.execute("""
                        UPDATE trades
                        SET setup_name = ?, setup_score = ?, daily_bias = ?, session_name = ?
                        WHERE trade_id = ?;
                    """, (
                        final_setup,
                        float(meta.get("setup_score", 0.0) or 0.0),
                        str(meta.get("daily_bias", "")),
                        str(meta.get("session_name", "")),
                        row["trade_id"],
                    ))
        except Exception:
            pass

    def _protect_open_trades_on_bias_reversal(self):
        """محافظت از پوزیشن‌های باز در سود هنگام چرخش شدید بایاس روزانه/چهارساعته (انتقال SL به Break-Even)"""
        now_ts = time.time()
        if (now_ts - self.last_bias_protect_check_time) < 60.0:
            return
        self.last_bias_protect_check_time = now_ts

        if not self.is_forex_session_open():
            return

        try:
            active_users = self.db.get_auto_trading_users()
            if not active_users:
                return

            bias_cache: Dict[str, str] = {}
            for user in active_users:
                user_id = user["user_id"]
                if not str(user.get("mt5_login", "")).strip():
                    continue
                open_trades = self.db.get_user_open_trades(user_id=user_id)
                if not open_trades:
                    continue

                target_keys = self._get_user_routing_keys(user_id)
                for t in open_trades:
                    ticket = int(t.get("mt5_ticket", 0) or 0)
                    if ticket <= 0:
                        continue
                    if (now_ts - self._bias_protect_last_ts.get(ticket, 0.0)) < 300.0:
                        continue

                    pnl = float(t.get("realized_pnl", 0.0) or 0.0)
                    if pnl <= 0.0:
                        continue

                    entry = float(t.get("entry_price", 0.0) or 0.0)
                    sl = float(t.get("stop_loss", 0.0) or 0.0)
                    tp = float(t.get("tp1", 0.0) or 0.0)
                    side = str(t.get("side", "BUY")).upper()
                    if entry <= 0.0:
                        continue

                    already_be = (side == "BUY" and sl >= entry) or (side == "SELL" and 0.0 < sl <= entry)
                    if already_be:
                        continue

                    canon_sym = self._match_canonical_symbol(str(t.get("symbol", "")))
                    if not canon_sym:
                        continue

                    if canon_sym not in bias_cache:
                        bundle = self.data_service.get_live_multitimeframe_bundle(canon_sym)
                        if not bundle:
                            bias_cache[canon_sym] = "NONE"
                        else:
                            _, bias_details = self.smc_engine.evaluate_daily_bias(
                                df_h4=bundle.get("df_h4"),
                                df_d1=bundle.get("df_d1"),
                            )
                            bias_cache[canon_sym] = str(bias_details.get("strong_reversal_to", "NONE"))

                    strong_rev = bias_cache[canon_sym]
                    is_opposite_reversal = (
                        (side == "BUY" and strong_rev == "BEARISH")
                        or (side == "SELL" and strong_rev == "BULLISH")
                    )
                    if not is_opposite_reversal:
                        continue

                    queued = account_config.queue_mt5_command(
                        target_keys,
                        {
                            "action": "MODIFY",
                            "ticket": ticket,
                            "symbol": str(t.get("symbol", canon_sym)),
                            "sl": round(entry, 5),
                            "tp": round(tp, 5) if tp > 0 else 0.0,
                        },
                        user_cfg=user,
                    )
                    if queued:
                        self._bias_protect_last_ts[ticket] = now_ts
                        print(
                            f"🛡️ [محافظت چرخش بایاس | تیکت #{ticket} {t.get('symbol')}]: "
                            f"چرخش شدید بایاس به {strong_rev} -> انتقال SL به نقطه ورود ({entry:.5f}).",
                            flush=True,
                        )
        except Exception:
            pass

    def _sync_binance_users_positions(self):
        """همگام‌سازی لحظه‌ای پوزیشن‌های باز صرافی بایننس با دیتابیس و پاکسازی حافظه پوزیشن‌های بسته‌شده"""
        now = time.time()
        if now - self.last_binance_sync_time < 15.0:
            return
        self.last_binance_sync_time = now

        try:
            active_users = self.db.get_auto_trading_users()
            for user in active_users:
                if not (user.get("binance_api_key") and user.get("binance_secret_key")):
                    continue
                live_pos = account_config.fetch_binance_open_positions(user)
                if live_pos is not None:
                    closed_ids = self.db.sync_binance_live_positions(user["user_id"], live_pos)
                    for cid in closed_ids:
                        if cid in self.trade_engine.open_positions:
                            del self.trade_engine.open_positions[cid]

            db_open_ids = {str(r["trade_id"]) for r in self.db.get_all_open_trades()}
            for pos_id in list(self.trade_engine.open_positions.keys()):
                if pos_id not in db_open_ids:
                    del self.trade_engine.open_positions[pos_id]
        except Exception:
            pass

    def manage_active_positions_fast(self):
        """مدیریت همگام‌سازی پوزیشن‌های باز با صرافی/بروکر، متادیتای یادگیری و محافظت بایاس"""
        self._sync_binance_users_positions()
        self._enrich_mt5_trade_metadata()
        self._protect_open_trades_on_bias_reversal()

    @staticmethod
    def _round_volume_to_step(raw_vol: float, specs: ContractSpecs) -> float:
        step = specs.volume_step if specs.volume_step > 0 else 0.01
        step_str = f"{step:.8f}".rstrip("0")
        decimals = len(step_str.split(".")[1]) if "." in step_str else 0
        vol = round(raw_vol, decimals)
        if vol < specs.min_volume:
            vol = specs.min_volume
        if vol > specs.max_volume:
            vol = specs.max_volume
        return vol

    @staticmethod
    def _is_symbol_already_open(
        canonical_symbol: str,
        user_cfg: Dict[str, Any],
        current_active: List[Dict[str, Any]],
    ) -> bool:
        """بررسی دقیق باز بودن معامله روی نماد (با پشتیبانی از نام‌های متفاوت بروکر مثل NDXUSD. و USTEC)"""
        candidates = {canonical_symbol.replace(" ", "").rstrip(".").upper()}
        resolved = account_config.resolve_broker_symbol(canonical_symbol, user_cfg)
        if resolved:
            candidates.add(resolved.replace(" ", "").rstrip(".").upper())
        aliases = account_config.BROKER_SYMBOL_ALIASES.get(canonical_symbol, [canonical_symbol])
        for alias in aliases:
            candidates.add(alias.replace(" ", "").rstrip(".").upper())

        for t in current_active:
            t_sym = str(t.get("symbol", "")).replace(" ", "").rstrip(".").upper()
            if not t_sym:
                continue
            if t_sym in candidates:
                return True
            for alias in aliases:
                a_clean = alias.rstrip(".").upper()
                if len(a_clean) >= 5 and t_sym.startswith(a_clean):
                    return True
                if a_clean in ("NDX", "SPX") and (
                    t_sym.startswith(f"{a_clean}USD")
                    or t_sym.startswith(f"{a_clean}500")
                    or t_sym.startswith(f"{a_clean}100")
                ):
                    return True
        return False

    def _detect_gold_fs5_ict_sweep_limit(
        self,
        bundle: Dict[str, Any],
        daily_bias: str,
        h1_trend: str,
    ) -> Optional[Dict[str, Any]]:
        """FS5: ICT Swing Liquidity Sweep + Displacement + FVG Retest روی M5 با هم‌راستایی H1/H4/D1"""
        df_m5 = bundle.get("df_ltf")
        if df_m5 is None or len(df_m5) < 35:
            return None
        if daily_bias == "NEUTRAL" and h1_trend == "RANGING":
            return None

        allow_buy = (h1_trend == "BULLISH" and daily_bias != "BEARISH") or (daily_bias == "BULLISH" and h1_trend != "BEARISH")
        allow_sell = (h1_trend == "BEARISH" and daily_bias != "BULLISH") or (daily_bias == "BEARISH" and h1_trend != "BULLISH")
        if allow_buy == allow_sell:
            return None

        direction = "BUY" if allow_buy else "SELL"
        df_c = df_m5.iloc[:-1].tail(55).reset_index(drop=True)
        if len(df_c) < 30:
            return None

        atr_s = self.crt_engine.calculate_atr(df_c)
        atr_m5 = float(atr_s.iloc[-1]) if len(atr_s) > 0 else 0.0
        if atr_m5 <= 0.0:
            return None

        swing_h, swing_l = self.crt_engine.detect_swings_causal(df_c)
        recent_start = max(0, len(df_c) - 4)
        recent_slice = df_c.iloc[recent_start:]
        low_rec = float(recent_slice["low"].min())
        high_rec = float(recent_slice["high"].max())
        last_close = float(df_c.iloc[-1]["close"])

        swept_lvl = None
        ref_id = ""
        if direction == "BUY":
            for s_idx in reversed(swing_l[swing_l].index.tolist()):
                if s_idx >= recent_start:
                    continue
                lvl = float(df_c.iloc[s_idx]["low"])
                if low_rec < lvl and last_close > lvl and (0.05 * atr_m5 <= (lvl - low_rec) <= 1.80 * atr_m5):
                    swept_lvl = lvl
                    ref_id = f"FS5_{df_c.iloc[s_idx]['timestamp']}"
                    break
        else:
            for s_idx in reversed(swing_h[swing_h].index.tolist()):
                if s_idx >= recent_start:
                    continue
                lvl = float(df_c.iloc[s_idx]["high"])
                if high_rec > lvl and last_close < lvl and (0.05 * atr_m5 <= (high_rec - lvl) <= 1.80 * atr_m5):
                    swept_lvl = lvl
                    ref_id = f"FS5_{df_c.iloc[s_idx]['timestamp']}"
                    break

        if swept_lvl is None or ref_id in self.gold_used_refs:
            return None

        is_disp = False
        for _, row in recent_slice.iterrows():
            rng_k = float(row["high"] - row["low"])
            if rng_k <= 0:
                continue
            is_dir = (float(row["close"]) > float(row["open"])) if direction == "BUY" else (float(row["close"]) < float(row["open"]))
            body_r = abs(float(row["close"] - row["open"])) / rng_k
            if is_dir and (rng_k / atr_m5) >= 1.15 and body_r >= 0.50:
                is_disp = True
                break
        if not is_disp:
            return None

        sw_ts = self.crt_engine._normalize_ts(df_c.iloc[recent_start]["timestamp"])
        exp_fvg = "BULLISH" if direction == "BUY" else "BEARISH"
        fvgs = [
            f for f in self.crt_engine.detect_fvgs(df_c, "M5")
            if f.direction == exp_fvg and self.crt_engine._normalize_ts(f.created_time) >= (sw_ts - pd.Timedelta(minutes=5))
        ]
        if not fvgs:
            return None

        fvg = fvgs[-1]
        fvg_mid = (fvg.top + fvg.bottom) * 0.5
        limit_px = (fvg.top * 0.5 + fvg_mid * 0.5) if direction == "BUY" else (fvg.bottom * 0.5 + fvg_mid * 0.5)
        sl_px = (low_rec - 0.15 * atr_m5) if direction == "BUY" else (high_rec + 0.15 * atr_m5)
        min_sl = max(0.55 * atr_m5, limit_px * 0.0005)
        sl_dist = abs(limit_px - sl_px)
        if sl_dist < min_sl:
            sl_dist = min_sl
            sl_px = (limit_px - sl_dist) if direction == "BUY" else (limit_px + sl_dist)
        if sl_dist > max(2.20 * atr_m5, limit_px * 0.0030):
            return None

        return {
            "ref_id": ref_id,
            "setup_name": "ICT_SWEEP_FVG",
            "direction": direction,
            "limit_px": limit_px,
            "sl_px": sl_px,
            "atr_m5": atr_m5,
            "daily_bias": daily_bias,
            "expires_ts": time.time() + 1500.0,
        }

    def _detect_gold_fs6_crt_m1_limit(
        self,
        bundle: Dict[str, Any],
        daily_bias: str,
        h1_trend: str,
    ) -> Optional[Dict[str, Any]]:
        """FS6: فست اسکالپ CRT M15 -> Sweep/MSS/FVG روی 1m با هم‌راستایی سخت‌گیرانه H1/H4/D1"""
        df_1m = bundle.get("df_1m")
        df_m15 = bundle.get("df_mtf")
        df_m5 = bundle.get("df_ltf")
        if df_1m is None or df_m15 is None or df_m5 is None:
            return None
        if len(df_1m) < 25 or len(df_m15) < 5 or len(df_m5) < 16:
            return None

        df_1m_c = df_1m.iloc[:-1].tail(65).reset_index(drop=True)
        df_m15_c = df_m15.iloc[:-1].reset_index(drop=True)
        df_m5_c = df_m5.iloc[:-1].reset_index(drop=True)

        atr_m5 = float(self.crt_engine.calculate_atr(df_m5_c).iloc[-1])
        atr_1m = float(self.crt_engine.calculate_atr(df_1m_c).iloc[-1])
        if atr_m5 <= 0 or atr_1m <= 0:
            return None

        last_1m = df_1m_c.iloc[-1]
        m1_ts = self.crt_engine._normalize_ts_series(df_1m_c["timestamp"])
        sh_1m, sl_1m = self.crt_engine.detect_swings_causal(df_1m_c)
        all_fvgs_1m = self.crt_engine.detect_fvgs(df_1m_c, "M1")

        for off in (-1, -2):
            if abs(off) > len(df_m15_c):
                continue
            r = df_m15_c.iloc[off]
            t0 = self.crt_engine._normalize_ts(r["timestamp"])
            ref_close_ts = t0 + pd.Timedelta(minutes=15)
            ref_high = float(r["high"])
            ref_low = float(r["low"])
            ref_id = f"FS6_{t0.isoformat()}"
            if ref_id in self.gold_used_refs:
                continue
            if (ref_high - ref_low) < (0.25 * atr_m5):
                continue

            since_ref = df_1m_c[m1_ts >= ref_close_ts]
            if since_ref.empty or len(since_ref) > 20:
                continue

            recent_1m = since_ref.tail(15)
            lowest_1m = float(recent_1m["low"].min())
            highest_1m = float(recent_1m["high"].max())

            min_pen, max_pen = 0.05 * atr_m5, 2.00 * atr_m5
            bull_sw = lowest_1m < ref_low and (min_pen <= (ref_low - lowest_1m) <= max_pen) and float(last_1m["close"]) > ref_low
            bear_sw = highest_1m > ref_high and (min_pen <= (highest_1m - ref_high) <= max_pen) and float(last_1m["close"]) < ref_high
            if bull_sw == bear_sw:
                continue

            direction = "BUY" if bull_sw else "SELL"
            if direction == "BUY" and (daily_bias == "BEARISH" or h1_trend == "BEARISH" or (daily_bias == "NEUTRAL" and h1_trend != "BULLISH")):
                continue
            if direction == "SELL" and (daily_bias == "BULLISH" or h1_trend == "BULLISH" or (daily_bias == "NEUTRAL" and h1_trend != "BEARISH")):
                continue

            sw_rel = int(recent_1m["low"].to_numpy().argmin()) if direction == "BUY" else int(recent_1m["high"].to_numpy().argmax())
            sw_ts = self.crt_engine._normalize_ts(recent_1m.iloc[sw_rel]["timestamp"])
            is_disp = False
            for _, row in recent_1m.iloc[sw_rel:].iterrows():
                rng_k = float(row["high"] - row["low"])
                if rng_k <= 0:
                    continue
                is_dir = (float(row["close"]) > float(row["open"])) if direction == "BUY" else (float(row["close"]) < float(row["open"]))
                if is_dir and (rng_k / atr_1m) >= 1.15 and (abs(float(row["close"] - row["open"])) / rng_k) >= 0.50:
                    is_disp = True
                    break
            if not is_disp:
                continue

            mss_ok = False
            if direction == "BUY" and float(last_1m["close"]) > ref_low:
                for s_idx in reversed(sh_1m[sh_1m].index.tolist()[-3:]):
                    post = df_1m_c.iloc[s_idx + 1:]
                    if len(post) > 0 and float(post["close"].max()) > float(df_1m_c.iloc[s_idx]["high"]):
                        mss_ok = True
                        break
            elif direction == "SELL" and float(last_1m["close"]) < ref_high:
                for s_idx in reversed(sl_1m[sl_1m].index.tolist()[-3:]):
                    post = df_1m_c.iloc[s_idx + 1:]
                    if len(post) > 0 and float(post["close"].min()) < float(df_1m_c.iloc[s_idx]["low"]):
                        mss_ok = True
                        break
            if not mss_ok:
                continue

            exp_fvg = "BULLISH" if direction == "BUY" else "BEARISH"
            fvgs = [
                f for f in all_fvgs_1m
                if f.direction == exp_fvg and self.crt_engine._normalize_ts(f.created_time) >= (sw_ts - pd.Timedelta(minutes=2))
            ]
            if not fvgs:
                continue

            fvg = fvgs[-1]
            fvg_mid = (fvg.top + fvg.bottom) * 0.5
            limit_px = (fvg.top * 0.5 + fvg_mid * 0.5) if direction == "BUY" else (fvg.bottom * 0.5 + fvg_mid * 0.5)
            sl_px = (lowest_1m - 0.15 * atr_m5) if direction == "BUY" else (highest_1m + 0.15 * atr_m5)
            min_sl = max(0.55 * atr_m5, limit_px * 0.0005)
            sl_dist = abs(limit_px - sl_px)
            if sl_dist < min_sl:
                sl_dist = min_sl
                sl_px = (limit_px - sl_dist) if direction == "BUY" else (limit_px + sl_dist)
            if sl_dist > max(2.20 * atr_m5, limit_px * 0.0030):
                return None

            return {
                "ref_id": ref_id,
                "setup_name": "CRT_M15_M1_FVG",
                "direction": direction,
                "limit_px": limit_px,
                "sl_px": sl_px,
                "atr_m5": atr_m5,
                "daily_bias": daily_bias,
                "expires_ts": time.time() + 600.0,
            }
        return None

    def _evaluate_gold_fast_scalp_opportunity(
        self,
        bundle: Dict[str, Any],
        current_price: float,
    ) -> Optional[Any]:
        """اجرای فست اسکالپ طلا (FS5 + FS6) با ریسک ثابت ۰.۵٪ در بازه 07:00-20:00 UTC"""
        now_ts = time.time()
        for k in [rk for rk, ts in self.gold_used_refs.items() if (now_ts - ts) > 86400.0]:
            del self.gold_used_refs[k]

        utc_hour = datetime.now(timezone.utc).hour
        if not (7 <= utc_hour < 20):
            self.gold_fast_pending = None
            return None

        if self.gold_fast_pending is None:
            daily_bias, _ = self.smc_engine.evaluate_daily_bias(
                df_h4=bundle.get("df_h4"),
                df_d1=bundle.get("df_d1"),
            )
            h1_smc = self.smc_engine.analyze_market(
                "XAUUSD",
                "FOREX_OR_INDICES",
                bundle["df_htf"],
                timeframe_label="H1",
                df_h4=bundle.get("df_h4"),
                df_d1=bundle.get("df_d1"),
            )
            h1_trend = str(h1_smc.trend_direction).upper()

            setup_cand = self._detect_gold_fs5_ict_sweep_limit(bundle, daily_bias, h1_trend)
            if setup_cand is None:
                setup_cand = self._detect_gold_fs6_crt_m1_limit(bundle, daily_bias, h1_trend)
            if setup_cand is not None:
                self.gold_fast_pending = setup_cand

        pend = self.gold_fast_pending
        if pend is None:
            return None

        if now_ts > float(pend["expires_ts"]):
            self.gold_fast_pending = None
            return None

        side = pend["direction"]
        sl_px = float(pend["sl_px"])
        limit_px = float(pend["limit_px"])
        atr_m5 = float(pend["atr_m5"])

        if (side == "BUY" and current_price <= sl_px) or (side == "SELL" and current_price >= sl_px):
            self.gold_fast_pending = None
            return None

        filled = (side == "BUY" and current_price <= limit_px) or (side == "SELL" and current_price >= limit_px)
        if not filled:
            return None

        sl_dist = abs(current_price - sl_px)
        min_sl = max(0.55 * atr_m5, current_price * 0.0005)
        if sl_dist < min_sl:
            sl_dist = min_sl
            sl_px = (current_price - sl_dist) if side == "BUY" else (current_price + sl_dist)
        if sl_dist > max(2.20 * atr_m5, current_price * 0.0030):
            self.gold_fast_pending = None
            return None

        self.gold_used_refs[pend["ref_id"]] = now_ts
        self.gold_fast_pending = None

        tp1 = (current_price + sl_dist * 1.1) if side == "BUY" else (current_price - sl_dist * 1.1)
        tp2 = (current_price + sl_dist * 1.5) if side == "BUY" else (current_price - sl_dist * 1.5)
        tp3 = (current_price + sl_dist * 2.0) if side == "BUY" else (current_price - sl_dist * 2.0)

        from ares_03_master_setup_engine import SetupOpportunity
        return SetupOpportunity(
            opportunity_id=f"OPP_XAUFS_{int(now_ts)}",
            symbol="XAUUSD",
            market="FOREX_OR_INDICES",
            direction=side,
            setup_name=pend["setup_name"],
            entry_price=current_price,
            stop_loss=sl_px,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward_ratio=2.0,
            total_score=80.0,
            score_breakdown={"gold_fast_scalp": 80.0},
            suggested_risk_pct=0.5,
            is_counter_trend=False,
            status="APPROVED",
            daily_bias=pend["daily_bias"],
            confirmations=[f"فست اسکالپ طلا ({pend['setup_name']}) در پولبک FVG با ریسک ثابت 0.5% تایید شد."],
        )

    def scan_for_opportunities(self):
        """اسکن واحد بازار و ارسال همزمان سیگنال به تمام اکانت‌های متصل و دارای ظرفیت با کنترل ریسک روزانه و افت سرمایه"""
        active_users = self.db.get_auto_trading_users()
        if not active_users:
            return

        now_ts = time.time()
        forex_session_open = self.is_forex_session_open()
        session_name = self.get_current_session_name()

        expired_keys = [k for k, t in self.pending_trade_locks.items() if now_ts - t > 900.0]
        for k in expired_keys:
            del self.pending_trade_locks[k]

        eligible_users: List[Dict[str, Any]] = []
        for user in active_users:
            user_id = user["user_id"]
            m_login = str(user.get("mt5_login", "")).strip()

            mt5_equity, mt5_ok = 0.0, False
            if m_login:
                mt5_equity, _, _, mt5_ok = account_config.fetch_user_live_balance(user)

            bin_equity, bin_ok = 0.0, False
            b_key = str(user.get("binance_api_key", "")).strip()
            b_sec = str(user.get("binance_secret_key", "")).strip()
            if b_key and b_sec:
                bin_equity, _, _, bin_ok = account_config.fetch_user_live_balance({
                    "binance_api_key": b_key,
                    "binance_secret_key": b_sec,
                })

            is_mt5_connected = mt5_ok and mt5_equity > 0
            is_binance_connected = bin_ok and bin_equity > 0

            mt5_risk_state = {"allowed": False, "daily_loss_pct": 0.0}
            if is_mt5_connected:
                mt5_state_key = f"{user_id}_mt5_{m_login}"
                mt5_risk_state = self.db.sync_and_check_user_risk_limits(mt5_state_key, user_id, mt5_equity)
                if not mt5_risk_state["allowed"]:
                    self._log_risk_alert_throttled(
                        mt5_state_key,
                        f"🛡️ [قفل محافظتی ریسک | متاتریدر {m_login}]: {mt5_risk_state['reason']}",
                    )
                    is_mt5_connected = False

            bin_risk_state = {"allowed": False, "daily_loss_pct": 0.0}
            if is_binance_connected:
                bin_state_key = f"{user_id}_bin"
                bin_risk_state = self.db.sync_and_check_user_risk_limits(bin_state_key, user_id, bin_equity)
                if not bin_risk_state["allowed"]:
                    self._log_risk_alert_throttled(
                        bin_state_key,
                        f"🛡️ [قفل محافظتی ریسک | بایننس کاربر {user.get('identifier')}]: {bin_risk_state['reason']}",
                    )
                    is_binance_connected = False

            if not is_mt5_connected and not is_binance_connected:
                continue

            target_keys = self._get_user_routing_keys(user_id)
            active_trades_db = self.db.get_user_open_trades(user_id=user_id)
            pending_queue_count = account_config.get_user_pending_commands_count(target_keys)
            if (len(active_trades_db) + pending_queue_count) >= 3:
                continue

            eligible_users.append({
                "user": user,
                "user_id": user_id,
                "mt5_equity": mt5_equity,
                "is_mt5_connected": is_mt5_connected,
                "mt5_daily_loss_pct": float(mt5_risk_state.get("daily_loss_pct", 0.0)),
                "bin_equity": bin_equity,
                "is_binance_connected": is_binance_connected,
                "bin_daily_loss_pct": float(bin_risk_state.get("daily_loss_pct", 0.0)),
                "target_keys": target_keys,
            })

        if not eligible_users:
            return

        for symbol, specs in self.SYMBOLS_SPECS.items():
            is_crypto = symbol in self.data_service.binance.CRYPTO_SYMBOLS
            if not is_crypto and not forex_session_open:
                continue

            clean_sym = symbol.replace(" ", "").rstrip(".")

            candidate_users: List[Dict[str, Any]] = []
            for u_ctx in eligible_users:
                user = u_ctx["user"]
                user_id = u_ctx["user_id"]
                target_keys = u_ctx["target_keys"]

                if is_crypto and not u_ctx["is_binance_connected"]:
                    continue
                if not is_crypto and not u_ctx["is_mt5_connected"]:
                    continue
                if not is_crypto and not account_config.is_symbol_tradable_for_user(symbol, user):
                    continue

                current_active = self.db.get_user_open_trades(user_id=user_id)
                current_pending = account_config.get_user_pending_commands_count(target_keys)
                if (len(current_active) + current_pending) >= 3:
                    continue

                lock_key = f"{user_id}_{clean_sym}"
                if lock_key in self.pending_trade_locks:
                    continue

                if self._is_symbol_already_open(symbol, user, current_active):
                    continue

                if not is_crypto:
                    broker_sym_check = account_config.resolve_broker_symbol(symbol, user)
                    if account_config.is_symbol_in_pending_queue(target_keys, broker_sym_check):
                        continue

                candidate_users.append(u_ctx)

            if not candidate_users:
                continue

            news_status = self.news_filter.is_news_restricted(symbol)
            if news_status["restricted"]:
                continue

            bundle = self.data_service.get_live_multitimeframe_bundle(symbol)
            if not bundle:
                continue

            last_candle = bundle["df_mtf"].iloc[-1]
            candle_ts_str = str(last_candle.get("timestamp", ""))

            fresh_candidates = [
                u_ctx for u_ctx in candidate_users
                if self.symbol_last_candle_time.get(f"{u_ctx['user_id']}_{clean_sym}") != candle_ts_str
            ]
            if not fresh_candidates:
                continue

            current_price = bundle["current_price"]
            market_type = bundle["market_type"]
            df_mtf = bundle["df_mtf"]
            df_mtf_closed = df_mtf.iloc[:-1] if len(df_mtf) > 2 else df_mtf
            atr_series = self.crt_engine.calculate_atr(df_mtf_closed)
            current_atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 else 0.0

            crt_res = self.crt_engine.evaluate_crt_setup(
                symbol, market_type, bundle["df_htf"], bundle["df_mtf"], bundle["df_ltf"]
            )
            smc_res = self.smc_engine.analyze_market(
                symbol,
                market_type,
                bundle["df_mtf"],
                df_h4=bundle.get("df_h4"),
                df_d1=bundle.get("df_d1"),
            )

            opportunity = self.setup_engine.evaluate_opportunity(
                crt_res.to_dict(),
                smc_res.to_dict(),
                current_price,
                session_valid=True,
                in_news_window=False,
                atr=current_atr,
            )

            self.db.record_setup_evaluation(opportunity.to_dict())

            if opportunity.status != "APPROVED" and symbol == "XAUUSD":
                fs_opp = self._evaluate_gold_fast_scalp_opportunity(bundle, current_price)
                if fs_opp is not None:
                    opportunity = fs_opp
                    self.db.record_setup_evaluation(opportunity.to_dict())

            if opportunity.status != "APPROVED":
                continue

            # سیستم یادگیری از گذشته: ارزیابی غلتان ستاپ با حداقل نمونه آماری N >= 15
            rolling_perf = self.db.get_setup_rolling_performance(opportunity.setup_name, window_size=30, min_samples=15)
            if rolling_perf.get("is_disabled"):
                self._log_risk_alert_throttled(
                    f"disabled_setup_{opportunity.setup_name}",
                    f"🧠 [یادگیری ARES]: {rolling_perf.get('reason')} — ورود متوقف شد.",
                )
                continue

            post_news = news_status.get("post_news_analysis", {})
            if post_news.get("has_data") and post_news.get("news_bias") != "NEUTRAL":
                print(f"📰 [{symbol}] {post_news.get('summary')}", flush=True)

            sl_dist = round(abs(opportunity.entry_price - opportunity.stop_loss), 6)
            tp_dist = round(sl_dist * 2.0, 6)
            order_comment = f"ARES|{opportunity.setup_name}"[:31]

            for u_ctx in fresh_candidates:
                user = u_ctx["user"]
                user_id = u_ctx["user_id"]
                target_keys = u_ctx["target_keys"]
                lock_key = f"{user_id}_{clean_sym}"
                candle_key = f"{user_id}_{clean_sym}"

                current_active = self.db.get_user_open_trades(user_id=user_id)
                current_pending = account_config.get_user_pending_commands_count(target_keys)
                if (len(current_active) + current_pending) >= 3:
                    continue

                trade_equity = u_ctx["bin_equity"] if is_crypto else u_ctx["mt5_equity"]
                daily_loss_pct = u_ctx["bin_daily_loss_pct"] if is_crypto else u_ctx["mt5_daily_loss_pct"]
                user_risk_engine = self._get_user_risk_engine(user_id, trade_equity)
                user_risk_engine.daily_realized_pnl = -(trade_equity * (daily_loss_pct / 100.0))
                user_risk_engine.daily_fees_paid = 0.0

                risk_decision = user_risk_engine.validate_risk_gate(opportunity.to_dict(), specs=specs)

                if not risk_decision.approved:
                    continue

                vol = self._round_volume_to_step(risk_decision.calculated_volume, specs)
                risk_usd = round(float(risk_decision.risk_amount_usd), 2)

                if is_crypto and u_ctx["is_binance_connected"]:
                    res = account_config.execute_binance_order_detailed(
                        user,
                        symbol=symbol,
                        side=opportunity.direction,
                        volume=vol,
                        stop_loss=opportunity.stop_loss,
                        take_profit=opportunity.take_profit_3,
                        sl_dist=sl_dist,
                        tp_dist=tp_dist,
                    )
                    if res.get("success"):
                        real_entry = float(res.get("entry_price") or opportunity.entry_price)
                        real_sl = float(res.get("stop_loss") or opportunity.stop_loss)
                        real_tp3 = float(res.get("take_profit") or opportunity.take_profit_3)
                        exec_vol = float(res.get("volume") or vol)
                        is_buy = opportunity.direction == "BUY"
                        tp1 = (real_entry + (sl_dist * 1.1)) if is_buy else (real_entry - (sl_dist * 1.1))
                        tp2 = (real_entry + (sl_dist * 1.5)) if is_buy else (real_entry - (sl_dist * 1.5))

                        ok_pos, pos_obj, _ = self.trade_engine.open_position(
                            symbol=symbol,
                            market="CRYPTO_FUTURES",
                            side_str=opportunity.direction,
                            entry_price=real_entry,
                            stop_loss=real_sl,
                            tp1=tp1,
                            tp2=tp2,
                            tp3=real_tp3,
                            allocated_volume=exec_vol,
                            risk_usd=risk_usd,
                            user_id=user_id,
                            mt5_ticket=0,
                            setup_name=opportunity.setup_name,
                            setup_score=round(float(opportunity.total_score), 1),
                            daily_bias=opportunity.daily_bias,
                            session_name=session_name,
                        )
                        if ok_pos and pos_obj:
                            old_id = pos_obj.position_id
                            bin_id = f"BIN_{res.get('order_id', old_id)}"
                            pos_obj.position_id = bin_id
                            self.trade_engine.open_positions[bin_id] = self.trade_engine.open_positions.pop(old_id)
                            self.db.record_new_trade(pos_obj.to_dict(), user_id=user_id)

                        self.pending_trade_locks[lock_key] = time.time()
                        self.symbol_last_candle_time[candle_key] = candle_ts_str
                        print(
                            f"\n🚀 [سفارش بایننس اجرا شد | کاربر {user.get('identifier')}]: {symbol} | ستاپ: {opportunity.setup_name} | ریسک: ${risk_usd}",
                            flush=True,
                        )
                else:
                    broker_symbol = account_config.resolve_broker_symbol(symbol, user)

                    queued = account_config.queue_mt5_command(target_keys, {
                        "action": opportunity.direction,
                        "symbol": broker_symbol,
                        "volume": vol,
                        "sl": round(opportunity.stop_loss, 5),
                        "tp": round(opportunity.take_profit_3, 5),
                        "sl_dist": sl_dist,
                        "tp_dist": tp_dist,
                        "risk_usd": risk_usd,
                        "comment": order_comment,
                        "setup_name": opportunity.setup_name,
                        "setup_score": round(float(opportunity.total_score), 1),
                        "daily_bias": opportunity.daily_bias,
                        "session_name": session_name,
                    }, user_cfg=user)

                    if queued:
                        self.pending_trade_locks[lock_key] = time.time()
                        self.symbol_last_candle_time[candle_key] = candle_ts_str
                        self.recent_order_metadata[f"{user_id}_{clean_sym}"] = {
                            "canonical_symbol": symbol,
                            "setup_name": opportunity.setup_name,
                            "setup_score": round(float(opportunity.total_score), 1),
                            "daily_bias": opportunity.daily_bias,
                            "session_name": session_name,
                            "ts": time.time(),
                        }

                        print(
                            f"\n📡 [ارسال همزمان به متاتریدر {user.get('mt5_login')}]: {broker_symbol} | {opportunity.direction} | "
                            f"ستاپ: {opportunity.setup_name} ({opportunity.total_score:.1f}) | بایاس: {opportunity.daily_bias} | "
                            f"ریسک: ${risk_usd} | تارگت نهایی 2.0R",
                            flush=True,
                        )

    def run_loop(self):
        print("\n🚀 ناظر هوشمند ۲۴ ساعته (حالت معاملات ۱۰۰٪ واقعی، کنترل سقف ۳ پوزیشن) فعال شد.\n", flush=True)
        scan_interval = 4.0
        self.last_scan_time = 0.0

        while True:
            try:
                current_time = time.time()
                self.manage_active_positions_fast()

                if current_time - self.last_scan_time >= scan_interval:
                    self.scan_for_opportunities()
                    self.last_scan_time = current_time

                time.sleep(1.0)

            except KeyboardInterrupt:
                sys.exit(0)
            except Exception as e:
                print(f"⚠️ پیام سیستم: {e}", flush=True)
                time.sleep(2.0)


if __name__ == "__main__":
    ares = AresMasterSystem()
    ares.run_loop()