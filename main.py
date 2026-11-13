"""
================================================================================
ARES AI TRADING SYSTEM
MASTER REAL-TIME ENGINE + MULTI-USER INTEGRATION (main.py)
VERSION: 14.3 (EXACT BROKER 1:1.5 R:R DISTANCE, BINANCE SL/TP & DB POSITION SYNC)
================================================================================
"""

import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
        # فارکس، انس طلا و شاخص‌ها (مخصوص متاتریدر ۵ با سقف حجم ایمن)
        "XAUUSD": ContractSpecs("XAUUSD", min_volume=0.01, max_volume=0.30, volume_step=0.01, tick_size=0.01, contract_size=100.0, min_notional_usd=1.0, leverage=100.0),
        "EURUSD": ContractSpecs("EURUSD", min_volume=0.01, max_volume=0.50, volume_step=0.01, tick_size=0.00001, contract_size=100000.0, min_notional_usd=1.0, leverage=100.0),
        "NASDAQ 100": ContractSpecs("NASDAQ 100", min_volume=0.01, max_volume=1.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        "S&P 500": ContractSpecs("S&P 500", min_volume=0.01, max_volume=1.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
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
        print("🏛 راه‌اندازی ربات هوشمند ARES (نسخه ۱۴.۳ - ریسک‌به‌ریوارد دقیق بروکر ۱:۱.۵ و تکمیل بایننس)")
        print("=" * 80)

        self.db = AresDatabaseManager()
        self.data_service = AresUnifiedDataService()
        self.news_filter = EconomicNewsFilter(blackout_window_minutes=30)
        self.crt_engine = CRTStrategyEngine()
        self.smc_engine = SMCICTStrategyEngine()
        self.setup_engine = MasterSetupEngine(min_rr_ratio=1.5)

        self.risk_engine = RiskManagementPortfolioEngine(initial_capital=100.0)
        self.trade_engine = TradePositionManagementEngine(mode=ExecutionMode.LIVE)
        self.last_scan_time: float = 0.0
        self.last_db_sync_time: float = 0.0
        self.last_binance_sync_time: float = 0.0

        # قفل‌های حافظه بلادرنگ جهت مهار ۱۰۰٪ تاخیر پاسخ متاتریدر/صرافی
        self.pending_trade_locks: Dict[str, float] = {}
        self.symbol_last_candle_time: Dict[str, str] = {}

        self._restore_open_positions_from_db()

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

    def _sync_binance_users_positions(self):
        """همگام‌سازی لحظه‌ای پوزیشن‌های باز صرافی بایننس با دیتابیس و موتور مدیریت پوزیشن"""
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
        except Exception:
            pass

    def manage_active_positions_fast(self):
        """مدیریت هوشمند پوزیشن‌های بایننس و همگام‌سازی با صرافی (معاملات MT5 مستقیماً در بروکر SL/TP دارند)"""
        self._sync_binance_users_positions()

        if not self.trade_engine.open_positions:
            return

        now = time.time()
        for pos_id, pos in list(self.trade_engine.open_positions.items()):
            # معاملات متاتریدر دارای SL/TP بومی دقیق در بروکر هستند و نباید با قیمت یاهو زودهنگام بسته شوند
            if pos.market != "CRYPTO_FUTURES":
                continue

            bundle = self.data_service.get_live_multitimeframe_bundle(pos.symbol)
            if not bundle:
                continue

            last_candle = bundle["df_ltf"].iloc[-1]
            specs = self.SYMBOLS_SPECS.get(pos.symbol)
            contract_size = specs.contract_size if specs else 1.0

            update = self.trade_engine.update_position_on_price_tick(
                position_id=pos_id,
                current_high=float(last_candle["high"]),
                current_low=float(last_candle["low"]),
                current_close=float(last_candle["close"]),
                contract_size=contract_size,
            )

            user_cfg = self.db.get_user_broker_config(pos.user_id)

            if update.get("events"):
                for ev in update["events"]:
                    print(f"\n⚡ [بایننس | کاربر {pos.user_id} | {pos.symbol}]: {ev}", flush=True)

                if pos.is_break_even and user_cfg.get("binance_api_key"):
                    account_config.update_binance_sl_to_breakeven(
                        user_cfg=user_cfg,
                        symbol=pos.symbol,
                        side=pos.side.value,
                        volume=pos.current_volume,
                        new_sl=pos.stop_loss,
                    )

            if update.get("status") == "CLOSED":
                pnl = update["position"]["realized_pnl"]
                print(f"\n🔔 [تسویه معامله بایننس {pos.symbol}]: سود/زیان = {pnl:+.2f}$", flush=True)

                if user_cfg.get("binance_api_key"):
                    account_config.close_binance_position(
                        user_cfg=user_cfg,
                        symbol=pos.symbol,
                        side=pos.side.value,
                        volume=pos.initial_volume,
                    )
                self.db.record_new_trade(update["position"], user_id=pos.user_id)
            elif update.get("status") == "OPEN" and (now - self.last_db_sync_time > 10.0):
                self.db.record_new_trade(update["position"], user_id=pos.user_id)
                self.last_db_sync_time = now

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

    def scan_for_opportunities(self):
        """اسکن بازار و ارسال سفارش با رعایت سقف ۳ معامله، نسبت دقیق 1:1.5 و ثبت کامل در دیتابیس"""
        active_users = self.db.get_auto_trading_users()
        if not active_users:
            return

        now_ts = time.time()

        # پاکسازی خودکار قفل‌های منقضی شده بعد از ۱۵ دقیقه (۹۰۰ ثانیه)
        expired_keys = [k for k, t in self.pending_trade_locks.items() if now_ts - t > 900.0]
        for k in expired_keys:
            del self.pending_trade_locks[k]

        for user in active_users:
            user_id = user["user_id"]
            equity, acc_info, broker_info, is_connected = account_config.fetch_user_live_balance(user)

            if not is_connected or equity <= 0:
                continue

            target_keys = self._get_user_routing_keys(user_id)

            is_mt5_connected = ("متاتریدر" in acc_info) or bool(user.get("mt5_login"))
            is_binance_connected = bool(user.get("binance_api_key") and user.get("binance_secret_key"))

            # ۱. شمارش همزمان: پوزیشن‌های فعال ثبت‌شده + سفارشات معلق در صف
            active_trades_db = self.db.get_user_open_trades(user_id=user_id)
            pending_queue_count = account_config.get_user_pending_commands_count(target_keys)
            total_in_flight = len(active_trades_db) + pending_queue_count

            if total_in_flight >= 3:
                continue

            for symbol, specs in self.SYMBOLS_SPECS.items():
                is_crypto = symbol in self.data_service.binance.CRYPTO_SYMBOLS

                if is_crypto and not is_binance_connected:
                    continue
                if not is_crypto and not is_mt5_connected:
                    continue

                current_active = self.db.get_user_open_trades(user_id=user_id)
                current_pending = account_config.get_user_pending_commands_count(target_keys)
                if (len(current_active) + current_pending) >= 3:
                    break

                clean_sym = symbol.replace(" ", "").rstrip(".")
                lock_key = f"{user_id}_{clean_sym}"

                # ۲. بررسی قفل فوری حافظه
                if lock_key in self.pending_trade_locks:
                    continue

                # ۳. بررسی وجود پوزیشن باز در دیتابیس
                if any(t["symbol"].replace(" ", "").rstrip(".") == clean_sym for t in current_active):
                    continue

                # ۴. بررسی وجود سفارش برای این نماد در صف متاتریدر
                if not is_crypto:
                    broker_sym_check = account_config.resolve_broker_symbol(symbol, user)
                    if account_config.is_symbol_in_pending_queue(target_keys, broker_sym_check):
                        continue

                news_status = self.news_filter.is_news_restricted(symbol)
                if news_status["restricted"]:
                    continue

                bundle = self.data_service.get_live_multitimeframe_bundle(symbol)
                if not bundle:
                    continue

                # ۵. استراحت کندلی
                last_candle = bundle["df_mtf"].iloc[-1]
                candle_ts_str = str(last_candle.get("timestamp", ""))
                candle_key = f"{user_id}_{clean_sym}"
                if self.symbol_last_candle_time.get(candle_key) == candle_ts_str:
                    continue

                current_price = bundle["current_price"]
                market_type = bundle["market_type"]

                crt_res = self.crt_engine.evaluate_crt_setup(
                    symbol, market_type, bundle["df_htf"], bundle["df_mtf"], bundle["df_ltf"]
                )
                smc_res = self.smc_engine.analyze_market(symbol, market_type, bundle["df_mtf"])

                opportunity = self.setup_engine.evaluate_opportunity(
                    crt_res.to_dict(), smc_res.to_dict(), current_price, session_valid=True, in_news_window=False
                )

                self.db.record_setup_evaluation(opportunity.to_dict())

                if opportunity.status == "APPROVED":
                    self.risk_engine.current_capital = equity
                    risk_decision = self.risk_engine.validate_risk_gate(opportunity.to_dict(), specs=specs)

                    if risk_decision.approved:
                        vol = self._round_volume_to_step(risk_decision.calculated_volume, specs)

                        # محاسبه دقیق فواصل SL و TP برای تضمین ۱۰۰٪ نسبت 1:1.5 روی قیمت واقعی صرافی/بروکر
                        sl_dist = round(abs(opportunity.entry_price - opportunity.stop_loss), 5)
                        tp_dist = round(sl_dist * 1.5, 5)

                        if is_crypto and is_binance_connected:
                            res = account_config.execute_binance_order_detailed(
                                user,
                                symbol=symbol,
                                side=opportunity.direction,
                                volume=vol,
                                stop_loss=opportunity.stop_loss,
                                take_profit=opportunity.take_profit_1,
                                sl_dist=sl_dist,
                                tp_dist=tp_dist,
                            )
                            if res.get("success"):
                                real_entry = float(res.get("entry_price") or opportunity.entry_price)
                                real_sl = float(res.get("stop_loss") or opportunity.stop_loss)
                                real_tp1 = float(res.get("take_profit") or opportunity.take_profit_1)
                                exec_vol = float(res.get("volume") or vol)
                                is_buy = opportunity.direction == "BUY"
                                tp2 = (real_entry + (sl_dist * 2.5)) if is_buy else (real_entry - (sl_dist * 2.5))
                                tp3 = (real_entry + (sl_dist * 4.0)) if is_buy else (real_entry - (sl_dist * 4.0))

                                ok_pos, pos_obj, _ = self.trade_engine.open_position(
                                    symbol=symbol,
                                    market="CRYPTO_FUTURES",
                                    side_str=opportunity.direction,
                                    entry_price=real_entry,
                                    stop_loss=real_sl,
                                    tp1=real_tp1,
                                    tp2=tp2,
                                    tp3=tp3,
                                    allocated_volume=exec_vol,
                                    risk_usd=risk_decision.risk_amount_usd,
                                    user_id=user_id,
                                    mt5_ticket=0,
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
                                    f"\n🚀 [سفارش بایننس اجرا و در دیتابیس ثبت شد]: {symbol} | شناسه: {res.get('order_id')} | "
                                    f"ورود: {real_entry} | SL: {real_sl} | TP: {real_tp1}",
                                    flush=True,
                                )
                        else:
                            broker_symbol = account_config.resolve_broker_symbol(symbol, user)

                            queued = account_config.queue_mt5_command(target_keys, {
                                "action": opportunity.direction,
                                "symbol": broker_symbol,
                                "volume": vol,
                                "sl": round(opportunity.stop_loss, 5),
                                "tp": round(opportunity.take_profit_1, 5),
                                "sl_dist": sl_dist,
                                "tp_dist": tp_dist,
                            }, user_cfg=user)

                            if queued:
                                self.pending_trade_locks[lock_key] = time.time()
                                self.symbol_last_candle_time[candle_key] = candle_ts_str

                                print(f"\n📡 [سیگنال تایید شد -> ارسال ۱ معامله امن با نسبت دقیق 1:1.5 به متاتریدر ۵]:", flush=True)
                                print(f"   نماد بروکر: {broker_symbol} | جهت: {opportunity.direction} | حجم امن: {vol} لات", flush=True)
                                print(f"   فاصله SL: {sl_dist} | فاصله TP (1:1.5): {tp_dist}", flush=True)
                                print(f"   🔒 قفل حفاظتی نماد {broker_symbol} برای ۱۵ دقیقه فعال شد.", flush=True)

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