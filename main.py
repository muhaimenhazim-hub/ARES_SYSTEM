"""
================================================================================
ARES AI TRADING SYSTEM
MASTER REAL-TIME ENGINE + MULTI-USER INTEGRATION (main.py)
VERSION: 11.0 (TURBO SPEED 1s POSITION CHECK & 5s OPPORTUNITY SCAN)
================================================================================
"""

import pprint
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

import account_config
from ares_01_crt_strategy_engine import CRTStrategyEngine
from ares_02_smc_ict_strategy_engine import SMCICTStrategyEngine
from ares_03_master_setup_engine import MasterSetupEngine
from ares_04_trade_position_management_engine import (
    ExecutionMode,
    PositionStatus,
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
        "BTCUSDT": ContractSpecs("BTCUSDT", min_volume=0.001, max_volume=50.0, volume_step=0.001, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ETHUSDT": ContractSpecs("ETHUSDT", min_volume=0.01, max_volume=100.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "BNBUSDT": ContractSpecs("BNBUSDT", min_volume=0.01, max_volume=100.0, volume_step=0.01, tick_size=0.1, contract_size=1.0, min_notional_usd=5.0, leverage=20.0),
        "ADAUSDT": ContractSpecs("ADAUSDT", min_volume=1.0, max_volume=10000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "XRPUSDT": ContractSpecs("XRPUSDT", min_volume=1.0, max_volume=10000.0, volume_step=1.0, tick_size=0.0001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "1000PEPEUSDT": ContractSpecs("1000PEPEUSDT", min_volume=100.0, max_volume=1000000.0, volume_step=100.0, tick_size=0.000001, contract_size=1.0, min_notional_usd=5.0, leverage=10.0),
        "XAUUSD": ContractSpecs("XAUUSD", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=100.0, min_notional_usd=1.0, leverage=100.0),
        "EURUSD": ContractSpecs("EURUSD", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.00001, contract_size=100000.0, min_notional_usd=1.0, leverage=100.0),
        "NASDAQ 100": ContractSpecs("NASDAQ 100", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
        "S&P 500": ContractSpecs("S&P 500", min_volume=0.01, max_volume=10.0, volume_step=0.01, tick_size=0.01, contract_size=1.0, min_notional_usd=1.0, leverage=50.0),
    }

    def __init__(self):
        print("=" * 80)
        print("🏛 راه‌اندازی ربات فوق‌سریع ARES (پایش هر ۱ ثانیه و اسکن هر ۵ ثانیه)")
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

    def manage_active_positions_fast(self):
        """مدیریت لحظه‌ای پوزیشن‌های باز با تیک‌های سریع قیمت"""
        if not self.trade_engine.open_positions:
            return

        for pos_id, pos in list(self.trade_engine.open_positions.items()):
            bundle = self.data_service.get_live_multitimeframe_bundle(pos.symbol)
            if not bundle:
                continue

            last_candle = bundle["df_ltf"].iloc[-1]
            update = self.trade_engine.update_position_on_price_tick(
                position_id=pos_id,
                current_high=float(last_candle["high"]),
                current_low=float(last_candle["low"]),
                current_close=float(last_candle["close"]),
            )

            if update.get("events"):
                for ev in update["events"]:
                    print(f"\n⚡ [کاربر {pos.user_id} | {pos.symbol}]: {ev}", flush=True)

                if pos.is_break_even:
                    account_config.queue_mt5_command(pos.user_id, {
                        "action": "MODIFY",
                        "symbol": pos.symbol,
                        "sl": pos.stop_loss,
                        "tp": pos.tp3,
                        "ticket": getattr(pos, "mt5_ticket", 0)
                    })

                if pos.partial_exits:
                    last_exit = pos.partial_exits[-1]
                    self.db.record_partial_exit({
                        "exit_id": last_exit.exit_id,
                        "target_name": last_exit.target_name,
                        "exit_price": last_exit.exit_price,
                        "closed_volume": last_exit.closed_volume,
                        "realized_pnl": last_exit.realized_pnl,
                        "fee_paid": last_exit.fee_paid,
                    }, trade_id=pos.position_id)

                self.db.record_new_trade(pos.to_dict(), user_id=pos.user_id)

            if update.get("status") == "CLOSED":
                pnl = update["position"]["realized_pnl"]
                print(f"\n🔔 [تسویه پوزیشن {pos.symbol}]: سود/زیان = {pnl:+.2f}$", flush=True)
                
                account_config.queue_mt5_command(pos.user_id, {
                    "action": "CLOSE",
                    "symbol": pos.symbol,
                    "ticket": getattr(pos, "mt5_ticket", 0)
                })
                self.db.record_new_trade(update["position"], user_id=pos.user_id)

    def scan_for_opportunities(self):
        active_users = self.db.get_auto_trading_users()
        if not active_users:
            return

        for user in active_users:
            user_id = user["user_id"]
            equity, acc_info, broker_info, is_connected = account_config.fetch_user_live_balance(user)

            if not is_connected or equity <= 0:
                continue

            active_trades_db = self.db.get_user_open_trades(user_id=user_id)
            if len(active_trades_db) >= 3:
                continue

            for symbol, specs in self.SYMBOLS_SPECS.items():
                current_active = self.db.get_user_open_trades(user_id=user_id)
                if len(current_active) >= 3:
                    break

                if any(t["symbol"] == symbol for t in current_active):
                    continue

                news_status = self.news_filter.is_news_restricted(symbol)
                if news_status["restricted"]:
                    continue

                bundle = self.data_service.get_live_multitimeframe_bundle(symbol)
                if not bundle:
                    continue

                current_price = bundle["current_price"]
                market_type = bundle["market_type"]

                crt_res = self.crt_engine.evaluate_crt_setup(symbol, market_type, bundle["df_htf"], bundle["df_mtf"], bundle["df_ltf"])
                smc_res = self.smc_engine.analyze_market(symbol, market_type, bundle["df_mtf"])

                opportunity = self.setup_engine.evaluate_opportunity(
                    crt_res.to_dict(), smc_res.to_dict(), current_price, session_valid=True, in_news_window=False
                )

                self.db.record_setup_evaluation(opportunity.to_dict())

                if opportunity.status == "APPROVED":
                    self.risk_engine.current_capital = equity
                    risk_decision = self.risk_engine.validate_risk_gate(opportunity.to_dict(), specs=specs)

                    if risk_decision.approved:
                        success, pos, msg = self.trade_engine.open_position(
                            symbol=symbol,
                            market=market_type,
                            side_str=opportunity.direction,
                            entry_price=opportunity.entry_price,
                            stop_loss=opportunity.stop_loss,
                            tp1=opportunity.take_profit_1,
                            tp2=opportunity.take_profit_2,
                            tp3=opportunity.take_profit_3,
                            allocated_volume=risk_decision.calculated_volume,
                            risk_usd=risk_decision.risk_amount_usd,
                            user_id=user_id,
                        )
                        if success:
                            print(f"\n🔥 [سیگنال تایید شد]: {symbol} {opportunity.direction} | ارسال فوری به متاتریدر...", flush=True)
                            self.db.record_new_trade(pos.to_dict(), user_id=user_id)

                            user_identifier = user.get("identifier", user_id)
                            account_config.queue_mt5_command(user_identifier, {
                                "action": opportunity.direction,
                                "symbol": symbol,
                                "volume": risk_decision.calculated_volume,
                                "sl": opportunity.stop_loss,
                                "tp": opportunity.take_profit_1,
                            })

    def run_loop(self):
        print("\n🚀 ناظر هوشمند با سرعت بالا فعال شد.\n", flush=True)
        scan_interval = 5.0  # اسکن سریع هر ۵ ثانیه
        self.last_scan_time = 0.0

        while True:
            try:
                current_time = time.time()
                # پایش پوزیشن‌های باز در هر ۱ ثانیه
                self.manage_active_positions_fast()

                if current_time - self.last_scan_time >= scan_interval:
                    self.scan_for_opportunities()
                    self.last_scan_time = current_time

                time.sleep(1.0)

            except KeyboardInterrupt:
                sys.exit(0)
            except Exception:
                time.sleep(1.0)


if __name__ == "__main__":
    ares = AresMasterSystem()
    ares.run_loop()