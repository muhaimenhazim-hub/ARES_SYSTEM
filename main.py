"""
================================================================================
ARES AI TRADING SYSTEM
MASTER REAL-TIME ENGINE + MULTI-USER INTEGRATION (main.py)
VERSION: 14.1 (ZERO GHOST TRADES, DYNAMIC BROKER SYMBOLS & DB CRASH-PROOF)
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
        # فارکس، انس طلا و شاخص‌ها (مخصوص متاتریدر ۵ با قابلیت تطبیق خودکار پسوند بروکر)
        "XAUUSD": ContractSpecs("XAUUSD", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=100.0, min_notional_usd=1.0, leverage=100.0),
        "EURUSD": ContractSpecs("EURUSD", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.00001, contract_size=100000.0, min_notional_usd=1.0, leverage=100.0),
        "NASDAQ 100": ContractSpecs("NASDAQ 100", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        "S&P 500": ContractSpecs("S&P 500", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        # کریپتو فیوچرز (فقط در صورت اتصال API بایننس)
        "BTCUSDT": ContractSpecs("BTCUSDT", min_volume=0.001, max_volume=50.0, volume_step=0.001, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ETHUSDT": ContractSpecs("ETHUSDT", min_volume=0.01, max_volume=100.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "BNBUSDT": ContractSpecs("BNBUSDT", min_volume=0.01, max_volume=100.0, volume_step=0.01, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ADAUSDT": ContractSpecs("ADAUSDT", min_volume=1.0, max_volume=10000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "XRPUSDT": ContractSpecs("XRPUSDT", min_volume=1.0, max_volume=10000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "1000PEPEUSDT": ContractSpecs("1000PEPEUSDT", min_volume=100.0, max_volume=1000000.0, volume_step=100.0, tick_size=0.000001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
    }

    def __init__(self):
        print("=" * 80)
        print("🏛 راه‌اندازی ربات هوشمند ARES (نسخه ۱۴.۱ - معاملات واقعی بروکر، بدون شبح)")
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

        # بازیابی پوزیشن‌های واقعی دارای تیکت متاتریدر
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

    def manage_active_positions_fast(self):
        """مدیریت هوشمند خروج پله‌ای و تریلینگ استاپ پوزیشن‌های واقعی"""
        if not self.trade_engine.open_positions:
            return

        now = time.time()
        for pos_id, pos in list(self.trade_engine.open_positions.items()):
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

            target_keys = self._get_user_routing_keys(pos.user_id)

            if update.get("events"):
                for ev in update["events"]:
                    print(f"\n⚡ [کاربر {pos.user_id} | {pos.symbol}]: {ev}", flush=True)

                if pos.is_break_even:
                    account_config.queue_mt5_command(target_keys, {
                        "action": "MODIFY",
                        "symbol": pos.symbol,
                        "sl": round(pos.stop_loss, 5),
                        "tp": round(pos.tp3, 5),
                        "ticket": getattr(pos, "mt5_ticket", 0),
                    })

            if update.get("status") == "CLOSED":
                pnl = update["position"]["realized_pnl"]
                print(f"\n🔔 [تسویه معامله بروکر {pos.symbol}]: سود/زیان = {pnl:+.2f}$", flush=True)

                account_config.queue_mt5_command(target_keys, {
                    "action": "CLOSE",
                    "symbol": pos.symbol,
                    "ticket": getattr(pos, "mt5_ticket", 0),
                })
                self.db.record_new_trade(update["position"], user_id=pos.user_id)
            elif update.get("status") == "OPEN" and (now - self.last_db_sync_time > 10.0):
                # به‌روزرسانی کنترل‌شده در دیتابیس (هر ۱۰ ثانیه یکبار به جای هر ثانیه)
                self.db.record_new_trade(update["position"], user_id=pos.user_id)
                self.last_db_sync_time = now

    def scan_for_opportunities(self):
        """اسکن بازار و ارسال مستقیم سفارشات تایید شده به متاتریدر ۵ بروکر"""
        active_users = self.db.get_auto_trading_users()
        if not active_users:
            return

        for user in active_users:
            user_id = user["user_id"]
            equity, acc_info, broker_info, is_connected = account_config.fetch_user_live_balance(user)

            if not is_connected or equity <= 0:
                continue

            is_mt5_connected = ("متاتریدر" in acc_info) or bool(user.get("mt5_login"))
            is_binance_connected = bool(user.get("binance_api_key") and user.get("binance_secret_key"))

            # بررسی تعداد معاملات واقعی باز کاربر در بروکر (سقف مجاز: ۳ معامله)
            active_trades_db = self.db.get_user_open_trades(user_id=user_id)
            if len(active_trades_db) >= 3:
                continue

            for symbol, specs in self.SYMBOLS_SPECS.items():
                is_crypto = symbol in self.data_service.binance.CRYPTO_SYMBOLS

                if is_crypto and not is_binance_connected:
                    continue
                if not is_crypto and not is_mt5_connected:
                    continue

                current_active = self.db.get_user_open_trades(user_id=user_id)
                if len(current_active) >= 3:
                    break

                # جلوگیری از ورود همزمان دو معامله روی یک جفت‌ارز
                clean_sym = symbol.replace(" ", "").rstrip(".")
                if any(t["symbol"].replace(" ", "").rstrip(".") == clean_sym for t in current_active):
                    continue

                news_status = self.news_filter.is_news_restricted(symbol)
                if news_status["restricted"]:
                    continue

                bundle = self.data_service.get_live_multitimeframe_bundle(symbol)
                if not bundle:
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
                        vol = round(risk_decision.calculated_volume, 2)
                        if vol < specs.min_volume:
                            vol = specs.min_volume

                        # ارسال واقعی سفارش به بایننس یا متاتریدر ۵ بروکر
                        if is_crypto and is_binance_connected:
                            success, order_id = account_config.execute_binance_order(
                                user,
                                symbol=symbol,
                                side=opportunity.direction,
                                volume=vol,
                                stop_loss=opportunity.stop_loss,
                                take_profit=opportunity.take_profit_1,
                            )
                            if success:
                                print(f"\n🚀 [سفارش بایننس اجرا شد]: {symbol} | شناسه: {order_id}", flush=True)
                        else:
                            # استخراج نماد واقعی مطابق با بروکر متاتریدر (شامل پسوندهایی مثل نقطه .)
                            broker_symbol = account_config.resolve_broker_symbol(symbol, user)
                            target_keys = self._get_user_routing_keys(user_id)

                            print(f"\n📡 [سیگنال تایید شد -> ارسال مستقیم به متاتریدر ۵ بروکر]:", flush=True)
                            print(f"   نماد بروکر: {broker_symbol} | جهت: {opportunity.direction} | حجم: {vol} لات", flush=True)
                            print(f"   ورود: {opportunity.entry_price} | حد ضرر: {opportunity.stop_loss} | حد سود: {opportunity.take_profit_1}", flush=True)

                            # ثبت سفارش در صف متاتریدر (بدون ثبت معامله فیک قبل از اجرا)
                            account_config.queue_mt5_command(target_keys, {
                                "action": opportunity.direction,
                                "symbol": broker_symbol,
                                "volume": vol,
                                "sl": round(opportunity.stop_loss, 5),
                                "tp": round(opportunity.take_profit_1, 5),
                            }, user_cfg=user)

    def run_loop(self):
        print("\n🚀 ناظر هوشمند ۲۴ ساعته (حالت معاملات ۱۰۰٪ واقعی بروکر) فعال شد.\n", flush=True)
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