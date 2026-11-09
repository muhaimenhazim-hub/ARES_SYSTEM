"""
================================================================================
ARES AI TRADING SYSTEM
FILE 05: RISK MANAGEMENT & PORTFOLIO CONTROL ENGINE
VERSION: 2.0 (SEAMLESS CAPITAL SYNC & DYNAMIC MICROLOT SIZING)
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class ContractSpecs:
    """مشخصات قراردادی نماد در صرافی یا بروکر متاتریدر ۵"""
    symbol: str
    min_volume: float
    max_volume: float
    volume_step: float
    tick_size: float
    contract_size: float
    min_notional_usd: float
    leverage: float = 100.0


@dataclass
class RiskGateDecision:
    """خروجی تصمیم‌گیری دروازه ریسک برای هر معامله"""
    decision_id: str
    opportunity_id: str
    symbol: str
    approved: bool
    calculated_volume: float
    risk_amount_usd: float
    risk_percentage: float
    required_margin_usd: float
    rejection_reasons: List[str] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "decision_id": self.decision_id,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "approved": self.approved,
            "calculated_volume": round(self.calculated_volume, 4),
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "risk_percentage": round(self.risk_percentage, 2),
            "required_margin_usd": round(self.required_margin_usd, 2),
            "rejection_reasons": self.rejection_reasons,
            "approvals": self.approvals,
            "timestamp": self.timestamp.isoformat(),
        }


class RiskManagementPortfolioEngine:
    """
    موتور مرکزی مدیریت ریسک و سرمایه ARES
    """

    def __init__(
        self,
        initial_capital: float = 100.0,
        max_daily_loss_pct: float = 3.0,
        max_daily_profit_pct: float = 5.0,
        max_drawdown_pct: float = 12.0,
        max_open_positions: int = 3,
        max_total_open_risk_pct: float = 3.0,
        loss_throttle_threshold_pct: float = 2.0,
        throttled_risk_pct: float = 0.25,
        correlation_threshold: float = 0.70,
    ):
        self._current_equity = initial_capital
        self.initial_capital = initial_capital
        self.peak_equity = initial_capital
        self.daily_realized_pnl = 0.0
        self.daily_fees_paid = 0.0

        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_daily_profit_pct = max_daily_profit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_open_positions = max_open_positions
        self.max_total_open_risk_pct = max_total_open_risk_pct
        self.loss_throttle_threshold_pct = loss_throttle_threshold_pct
        self.throttled_risk_pct = throttled_risk_pct
        self.correlation_threshold = correlation_threshold

        self.active_positions: Dict[str, Dict] = {}
        self.is_system_halted: bool = False
        self.halt_reason: Optional[str] = None

    # تطبیق دوگانه current_capital و current_equity جهت رفع باگ عدم اعمال موجودی زنده
    @property
    def current_capital(self) -> float:
        return self._current_equity

    @current_capital.setter
    def current_capital(self, value: float):
        val = float(value)
        if val > 0:
            self._current_equity = val
            if self._current_equity > self.peak_equity:
                self.peak_equity = self._current_equity

    @property
    def current_equity(self) -> float:
        return self._current_equity

    @current_equity.setter
    def current_equity(self, value: float):
        self.current_capital = value

    def update_account_state(self, current_equity: float, realized_pnl_delta: float = 0.0, fee_delta: float = 0.0):
        self.current_capital = current_equity
        self.daily_realized_pnl += realized_pnl_delta
        self.daily_fees_paid += fee_delta

        dd_pct = ((self.peak_equity - self._current_equity) / self.peak_equity) * 100.0 if self.peak_equity > 0 else 0.0
        if dd_pct >= self.max_drawdown_pct:
            self.is_system_halted = True
            self.halt_reason = f"افت سرمایه بحرانی ({dd_pct:.2f}٪) فراتر از سقف مجاز {self.max_drawdown_pct}٪ رخ داد. ورود موقتاً متوقف شد."

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        risk_usd: float,
        specs: ContractSpecs,
    ) -> Tuple[float, float, float]:
        """محاسبه دقیق علمی حجم معامله متناسب با گام نماد و لوریج متاتریدر/بایننس"""
        loss_per_unit = abs(entry_price - stop_loss_price) * specs.contract_size
        if loss_per_unit <= 0:
            return specs.min_volume, 0.0, 0.0

        raw_volume = risk_usd / loss_per_unit

        step = specs.volume_step
        if step > 0:
            rounded_volume = np.round(raw_volume / step) * step
            rounded_volume = round(rounded_volume, 4)
        else:
            rounded_volume = round(raw_volume, 4)

        if rounded_volume < specs.min_volume:
            rounded_volume = specs.min_volume
        elif rounded_volume > specs.max_volume:
            rounded_volume = specs.max_volume

        notional_value = rounded_volume * entry_price * specs.contract_size
        effective_leverage = specs.leverage if specs.leverage > 0 else 100.0
        required_margin = notional_value / effective_leverage

        return rounded_volume, notional_value, required_margin

    def validate_risk_gate(
        self,
        opportunity: Dict,
        specs: ContractSpecs,
        returns_df: Optional[pd.DataFrame] = None,
    ) -> RiskGateDecision:
        decision_id = f"GATE_{uuid.uuid4().hex[:8]}"
        opp_id = opportunity.get("opportunity_id", "N/A")
        symbol = opportunity.get("symbol", specs.symbol)
        rejections: List[str] = []
        approvals: List[str] = []

        if self.is_system_halted:
            return RiskGateDecision(
                decision_id=decision_id,
                opportunity_id=opp_id,
                symbol=symbol,
                approved=False,
                calculated_volume=0.0,
                risk_amount_usd=0.0,
                risk_percentage=0.0,
                required_margin_usd=0.0,
                rejection_reasons=[f"سیستم در توقف حفاظتی است: {self.halt_reason}"],
            )

        daily_loss_pct = (abs(min(0.0, self.daily_realized_pnl - self.daily_fees_paid)) / self._current_equity) * 100.0 if self._current_equity > 0 else 0.0
        if daily_loss_pct >= self.max_daily_loss_pct:
            return RiskGateDecision(
                decision_id=decision_id,
                opportunity_id=opp_id,
                symbol=symbol,
                approved=False,
                calculated_volume=0.0,
                risk_amount_usd=0.0,
                risk_percentage=0.0,
                required_margin_usd=0.0,
                rejection_reasons=[f"سقف زیان روزانه ({self.max_daily_loss_pct}٪) فعال شد."],
            )

        # درصد ریسک بر مبنای امتیاز ستاپ هوش مصنوعی
        suggested_risk = opportunity.get("scoring", {}).get("suggested_risk_pct", 1.0)
        final_risk_pct = self.throttled_risk_pct if daily_loss_pct >= self.loss_throttle_threshold_pct else suggested_risk
        risk_usd = (self._current_equity * final_risk_pct) / 100.0

        entry_price = float(opportunity.get("entry_price", opportunity.get("pricing", {}).get("entry_price", 0.0)))
        stop_loss = float(opportunity.get("stop_loss", opportunity.get("pricing", {}).get("stop_loss", 0.0)))

        volume, notional, margin = self.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            risk_usd=risk_usd,
            specs=specs,
        )

        if margin > (self._current_equity * 0.90):
            rejections.append("مارجین سفارش از سقف مجاز ۹۰٪ سرمایه آزاد بالاتر است.")

        is_approved = (len(rejections) == 0)
        if is_approved:
            approvals.append("معامله از تمام فیلترهای کنترل ریسک با موفقیت عبور کرد.")

        return RiskGateDecision(
            decision_id=decision_id,
            opportunity_id=opp_id,
            symbol=symbol,
            approved=is_approved,
            calculated_volume=volume,
            risk_amount_usd=risk_usd,
            risk_percentage=final_risk_pct,
            required_margin_usd=margin,
            rejection_reasons=rejections,
            approvals=approvals,
        )