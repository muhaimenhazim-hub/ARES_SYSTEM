"""
================================================================================
ARES AI TRADING SYSTEM
MASTER REAL-TIME ENGINE + DATABASE INTEGRATION (main.py)
VERSION: 4.1 (DYNAMIC REAL BALANCE & ZERO MOCK DATA)
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
    """
    هسته اصلی و ناظر هوشمند ARES مجهز به اتصال مستقیم به موجودی واقعی و پایگاه داده
    """

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
        print("🏛️ راه‌اندازی ربات خودکار ARES (بدون دیتای فرضی | متصل به اکانت واقعی)")
        print("=" * 80)

        self.db = AresDatabaseManager()
        self.data_service = AresUnifiedDataService()
        self.news_filter = EconomicNewsFilter(blackout_window_minutes=30)
        self.crt_engine = CRTStrategyEngine()
        self.smc_engine = SMCICTStrategyEngine()
        self.setup_engine = MasterSetupEngine(min_rr_ratio=1.5)

        # دریافت موجودی واقعی از کانفیگ
        real_equity, acc_info, broker_info, is_connected = account_config.fetch_live_account_balance()
        self.current_equity = real_equity

        print(f"📡 وضعیت اکانت: {acc_info}")
        print(f"💰 موجودی اولیه واقعی: {self.current_equity:.2f} USD")

        self.risk_engine = RiskManagementPortfolioEngine(initial_capital=max(self.current_equity, 1.0))
        self.trade_engine = TradePositionManagementEngine(mode=ExecutionMode.PAPER)
        self.last_scan_time: float = 0.0

    def sync_account_balance(self):
        """همگام‌سازی لحظه‌ای موجودی در صورت تغییر در داشبورد وب"""
        real_equity, acc_info, broker_info, is_connected = account_config.fetch_live_account_balance()
        if is_connected and real_equity > 0:
            self.current_equity = real_equity
            self.risk_engine.update_account_state(new_equity=real_equity)

    def manage_active_positions_fast(self):
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
                    print(f"\n⚡️ [اقدام سریع روی {pos.symbol}]: {ev}", flush=True)

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

                self.db.record_new_trade(pos.to_dict())

            if update.get("status") == "CLOSED":
                pnl = update["position"]["realized_pnl"]
                print(f"\n🔔 [تسویه معامله]: {pos.symbol} با سود/زیان {pnl:+.2f} دلار بسته شد.", flush=True)
                self.db.record_new_trade(update["position"])
                new_equity = self.risk_engine.current_equity + pnl
                self.risk_engine.update_account_state(new_equity, realized_pnl_delta=pnl)

    def scan_for_opportunities(self):
        self.sync_account_balance()

        # اگر حسابی متصل نباشد یا موجودی صفر باشد، پوزیشنی باز نمی‌شود
        if self.current_equity <= 0:
            return

        open_count = len(self.trade_engine.open_positions)
        if open_count >= self.risk_engine.max_open_positions:
            return

        for symbol, specs in self.SYMBOLS_SPECS.items():
            if any(p.symbol == symbol for p in self.trade_engine.open_positions.values()):
                continue

            if len(self.trade_engine.open_positions) >= self.risk_engine.max_open_positions:
                break

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
                    )
                    if success:
                        print(f"\n🔥 [معامله جدید در دیتابیس ثبت شد]: {symbol} | جهت: {opportunity.direction} | نمره: {opportunity.total_score}/100", flush=True)
                        self.db.record_new_trade(pos.to_dict())

    def run_loop(self):
        print("\n🚀 ناظر هوشمند سیستم فعال شد.")
        print("   - پایش قیمت‌ها: هر ۲ ثانیه یک‌بار")
        print("   - ذخیره‌سازی رویدادها در پایگاه داده")
        print("برای توقف اضطراری، کلیدهای Ctrl + C را بزنید.\n", flush=True)

        scan_interval = 60.0
        self.last_scan_time = 0.0

        while True:
            try:
                current_time = time.time()
                self.manage_active_positions_fast()

                if current_time - self.last_scan_time >= scan_interval:
                    self.scan_for_opportunities()
                    self.last_scan_time = current_time

                    db_summary = self.db.get_portfolio_summary()
                    conn_text = f"{self.current_equity:.2f}$" if self.current_equity > 0 else "عدم اتصال (0.00$)"
                    print(f"⏱ [پایش زنده]: سرمایه واقعی: {conn_text} | سود دیتابیس: {db_summary['net_realized_pnl_usd']:+.2f}$ | معاملات باز: {len(self.trade_engine.open_positions)}", flush=True)

                time.sleep(2.0)

            except KeyboardInterrupt:
                print("\n🛑 ربات متوقف شد.", flush=True)
                sys.exit(0)
            except Exception as e:
                time.sleep(2.0)


if __name__ == "__main__":
    ares = AresMasterSystem()
    ares.run_loop()