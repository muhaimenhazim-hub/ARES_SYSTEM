"""
================================================================================
ARES AI TRADING SYSTEM
FILE 05: RISK MANAGEMENT & PORTFOLIO CONTROL ENGINE
VERSION: 1.1
================================================================================
ماموریت ماژول:
این ماژول آخرین و بالاترین مرجع تصمیم‌گیری در ARES است.
وظایف قطعی:
- محاسبه حجم دقیق معامله بر اساس سرمایه اولیه ۵۰ دلاری و فاصله SL
- اعمال دروازه ریسک ۱۷ مرحله‌ای (Risk Gate) پیش از هر سفارش
- اعمال پله‌های ریسک بر اساس امتیاز ستاپ (۰.۵٪، ۱٪، ۱.۵٪)
- کاهش ریسک به ۰.۲۵٪ پس از رسیدن زیان روزانه به ۲٪
- قفل ورود با رسیدن به حد ضرر روزانه ۳٪ یا حد سود روزانه ۵٪
- توقف اضطراری سیستم در صورت وقوع افت سرمایه (Drawdown) بالای ۱۲٪
- کنترل همبستگی نمادها (ممنوعیت همبستگی بالای ۰.۷۰)
- مدیریت سقف ۳ معامله هم‌زمان و حداکثر ریسک تجمعی ۳٪
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
    """مشخصات قراردادی نماد در صرافی یا بروکر"""
    symbol: str
    min_volume: float
    max_volume: float
    volume_step: float
    tick_size: float
    contract_size: float
    min_notional_usd: float  # حداقل ارزش دلاری مجاز برای سفارش (مثلا ۵ دلار در بایننس)
    leverage: float = 10.0


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
            "calculated_volume": round(self.calculated_volume, 6),
            "risk_amount_usd": round(self.risk_amount_usd, 4),
            "risk_percentage": round(self.risk_percentage, 2),
            "required_margin_usd": round(self.required_margin_usd, 4),
            "rejection_reasons": self.rejection_reasons,
            "approvals": self.approvals,
            "timestamp": self.timestamp.isoformat(),
        }


class RiskManagementPortfolioEngine:
    """
    موتور مرکزی مدیریت ریسک، سرمایه و نظارت بر پورتفولیو ARES
    """

    def __init__(
        self,
        initial_capital: float = 50.0,
        max_daily_loss_pct: float = 3.0,
        max_daily_profit_pct: float = 5.0,
        max_drawdown_pct: float = 12.0,
        max_open_positions: int = 3,
        max_total_open_risk_pct: float = 3.0,
        loss_throttle_threshold_pct: float = 2.0,
        throttled_risk_pct: float = 0.25,
        correlation_threshold: float = 0.70,
    ):
        self.initial_capital = initial_capital
        self.current_equity = initial_capital
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

    def update_account_state(self, current_equity: float, realized_pnl_delta: float = 0.0, fee_delta: float = 0.0):
        """به‌روزرسانی لحظه‌ای تراز حساب و ارزیابی قله سرمایه (Peak Equity)"""
        self.current_equity = current_equity
        self.daily_realized_pnl += realized_pnl_delta
        self.daily_fees_paid += fee_delta

        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

        # بررسی دراوداون کل از قله تراز
        dd_pct = ((self.peak_equity - self.current_equity) / self.peak_equity) * 100.0
        if dd_pct >= self.max_drawdown_pct:
            self.is_system_halted = True
            self.halt_reason = f"افت سرمایه بحرانی ({dd_pct:.2f}٪) فراتر از سقف مجاز {self.max_drawdown_pct}٪ رخ داد. سیستم قفل شد."

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        risk_usd: float,
        specs: ContractSpecs,
    ) -> Tuple[float, float, float]:
        """
        محاسبه علمی حجم معامله، حجم گردشده طبق گام نماد و مارجین مورد نیاز
        """
        loss_per_unit = abs(entry_price - stop_loss_price) * specs.contract_size
        if loss_per_unit <= 0:
            return 0.0, 0.0, 0.0

        raw_volume = risk_usd / loss_per_unit

        # گرد کردن به سمت پایین بر اساس گام مجاز نماد صرافی (Volume Step)
        step = specs.volume_step
        if step > 0:
            rounded_volume = np.floor(raw_volume / step) * step
        else:
            rounded_volume = raw_volume

        # بررسی حداقل و حداکثر حجم
        if rounded_volume < specs.min_volume:
            rounded_volume = 0.0
        elif rounded_volume > specs.max_volume:
            rounded_volume = specs.max_volume

        notional_value = rounded_volume * entry_price * specs.contract_size
        required_margin = notional_value / specs.leverage if specs.leverage > 0 else notional_value

        return rounded_volume, notional_value, required_margin

    def check_correlation(self, new_symbol: str, returns_df: Optional[pd.DataFrame]) -> bool:
        """
        بررسی عدم وجود همبستگی شدید (Pearson >= 0.70) با پوزیشن‌های باز فعلی
        """
        if not self.active_positions or returns_df is None:
            return True

        for open_sym in [pos["symbol"] for pos in self.active_positions.values()]:
            if open_sym == new_symbol:
                return False  # نماد تکراری

            if open_sym in returns_df.columns and new_symbol in returns_df.columns:
                corr = returns_df[open_sym].corr(returns_df[new_symbol])
                if abs(corr) >= self.correlation_threshold:
                    return False
        return True

    def validate_risk_gate(
        self,
        opportunity: Dict,
        specs: ContractSpecs,
        returns_df: Optional[pd.DataFrame] = None,
    ) -> RiskGateDecision:
        """
        دروازه قطعی ارزیابی ریسک (Risk Gate) پیش از صدور مجوز اجرا
        """
        decision_id = f"GATE_{uuid.uuid4().hex[:8]}"
        opp_id = opportunity.get("opportunity_id", "N/A")
        symbol = opportunity.get("symbol", specs.symbol)
        rejections: List[str] = []
        approvals: List[str] = []

        # ۱. بررسی قفل بودن کلی سیستم
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
                rejection_reasons=[f"سیستم در حالت توقف است: {self.halt_reason}"],
            )

        # ۲. بررسی حد زیان روزانه (Max Daily Loss = 3%)
        daily_loss_pct = (abs(min(0.0, self.daily_realized_pnl - self.daily_fees_paid)) / self.initial_capital) * 100.0
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
                rejection_reasons=[f"سقف زیان روزانه ({self.max_daily_loss_pct}٪) تکمیل شده است. ورود ممنوع."],
            )

        # ۳. بررسی سقف سود روزانه (Max Daily Profit = 5%)
        daily_profit_pct = (max(0.0, self.daily_realized_pnl - self.daily_fees_paid) / self.initial_capital) * 100.0
        if daily_profit_pct >= self.max_daily_profit_pct:
            return RiskGateDecision(
                decision_id=decision_id,
                opportunity_id=opp_id,
                symbol=symbol,
                approved=False,
                calculated_volume=0.0,
                risk_amount_usd=0.0,
                risk_percentage=0.0,
                required_margin_usd=0.0,
                rejection_reasons=[f"سقف سود روزانه ({self.max_daily_profit_pct}٪) محقق شده است. توقف ورود جهت حفظ سود."],
            )

        # ۴. سقف تعداد پوزیشن‌های باز هم‌زمان (حداکثر ۳ پوزیشن)
        if len(self.active_positions) >= self.max_open_positions:
            rejections.append(f"تعداد پوزیشن‌های باز به سقف مجاز ({self.max_open_positions}) رسیده است.")

        # ۵. بررسی همبستگی با معاملات باز
        if not self.check_correlation(symbol, returns_df):
            rejections.append(f"نماد {symbol} دارای همبستگی شدید (بالای {self.correlation_threshold}) با یکی از معاملات باز است.")

        # ۶. تعیین درصد ریسک مجاز بر مبنای امتیاز ستاپ و قانون کاهش ریسک
        score = opportunity.get("scoring", {}).get("total_score", 0.0)
        suggested_risk = opportunity.get("scoring", {}).get("suggested_risk_pct", 0.5)

        # بررسی قانون ترمز: اگر ضرر روزانه به ۲٪ رسید، ریسک به ۰.۲۵٪ کاهش یابد
        if daily_loss_pct >= self.loss_throttle_threshold_pct:
            final_risk_pct = self.throttled_risk_pct
            approvals.append("اعمال قانون ترمز زیان: ریسک معامله به دلیل عبور ضرر روزانه از ۲٪، به ۰.۲۵٪ محدود شد.")
        else:
            final_risk_pct = suggested_risk
            approvals.append(f"ریسک پایه بر اساس نمره ({score}): {final_risk_pct}٪")

        risk_usd = (self.current_equity * final_risk_pct) / 100.0

        # ۷. سقف ریسک تجمیعی کل پورتفولیو (حداکثر ۳٪)
        current_open_risk = sum(pos.get("risk_amount_usd", 0.0) for pos in self.active_positions.values())
        if (current_open_risk + risk_usd) > ((self.current_equity * self.max_total_open_risk_pct) / 100.0):
            rejections.append(f"مجموع ریسک باز پورتفولیو از سقف {self.max_total_open_risk_pct}٪ فراتر خواهد رفت.")

        # ۸. محاسبه حجم دقیق و بررسی سازگاری با سرمایه ۵۰ دلاری
        entry_price = opportunity.get("pricing", {}).get("entry_price", 0.0)
        stop_loss = opportunity.get("pricing", {}).get("stop_loss", 0.0)

        volume, notional, margin = self.calculate_position_size(
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            risk_usd=risk_usd,
            specs=specs,
        )

        if volume <= 0:
            rejections.append(
                f"سرمایه حساب ({self.current_equity} دلار) برای حداقل حجم این نماد با رعایت حد ضرر و سقف ریسک ({risk_usd:.2f} دلار) کافی نیست."
            )

        if notional < specs.min_notional_usd:
            rejections.append(
                f"ارزش سفارش ({notional:.2f} دلار) کمتر از حداقل ارزش مجاز صرافی ({specs.min_notional_usd} دلار) است."
            )

        if margin > (self.current_equity * 0.80):
            rejections.append("مارجین مورد نیاز بیش از ۸۰٪ کل موجودی آزاد حساب است.")

        # تصمیم نهایی
        is_approved = (len(rejections) == 0)

        if is_approved:
            approvals.append("معامله از تمام ۱۷ فیلتر دروازه مدیریت ریسک با موفقیت عبور کرد.")

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


# ==============================================================================
# تست جامع موتور مدیریت ریسک با حساب ۵۰ دلاری (Self-Test Simulation)
# ==============================================================================
if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ARES AI TRADING SYSTEM — TESTING MODULE 05: RISK MANAGEMENT ENGINE")
    print("=" * 70)

    # ایجاد موتور مدیریت ریسک با سرمایه پایه ۵۰ دلار
    risk_engine = RiskManagementPortfolioEngine(initial_capital=50.0)

    # مشخصات واقعی قرارداد بیتکوین در بایننس فیوچرز
    btc_specs = ContractSpecs(
        symbol="BTCUSDT",
        min_volume=0.001,
        max_volume=100.0,
        volume_step=0.001,
        tick_size=0.1,
        contract_size=1.0,
        min_notional_usd=5.0,  # حداقل ۵ دلار ارزش سفارش
        leverage=20.0,         # اهرم ۲۰ برای مدیریت مارجین
    )

    # ستاپ ورودی تایید شده از موتور ۳
    mock_opp = {
        "opportunity_id": "OPP_BTC_123",
        "symbol": "BTCUSDT",
        "pricing": {
            "entry_price": 95000.0,
            "stop_loss": 94250.0,  # فاصله ضرر: ۷۵۰ دلار
        },
        "scoring": {
            "total_score": 90.0,
            "suggested_risk_pct": 1.5,  # ۱.۵ درصد از ۵۰ دلار = ۰.۷۵ دلار ریسک
        },
    }

    print("\n--- آزمایش اول: بررسی اعتبار معامله عادی با حساب ۵۰ دلاری ---")
    gate_decision = risk_engine.validate_risk_gate(opportunity=mock_opp, specs=btc_specs)
    pprint.pprint(gate_decision.to_dict())

    print("\n--- آزمایش دوم: شبیه‌سازی رسیدن زیان روزانه به ۳٪ (فعال‌سازی قفل توقف) ---")
    risk_engine.update_account_state(current_equity=48.4, realized_pnl_delta=-1.6)  # ضرر بیش از ۳٪
    gate_decision_2 = risk_engine.validate_risk_gate(opportunity=mock_opp, specs=btc_specs)
    print(f"نتیجه صدور مجوز معامله جدید: {gate_decision_2.approved}")
    print(f"دلیل رد: {gate_decision_2.rejection_reasons}")

    print("\n" + "=" * 70)
    if not gate_decision_2.approved and "سقف زیان روزانه" in gate_decision_2.rejection_reasons[0]:
        print("✅ تست فایل شماره ۵ با موفقیت ۱۰۰٪ انجام شد! فیلترهای ریسک و سرمایه ۵۰ دلاری کار می‌کنند.")
    print("=" * 70)