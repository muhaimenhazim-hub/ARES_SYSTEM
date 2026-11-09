"""
================================================================================
ARES AI TRADING SYSTEM
FILE 03: MASTER SETUP ENGINE
VERSION: 2.0 (PYTHON 3.12+ COMPLIANT & 5-DECIMAL MULTI-ASSET PRECISION)
================================================================================
ماموریت ماژول:
این ماژول مغز تصمیم‌گیری استراتژیک سیستم ARES است.
وظایف:
- دریافت نتایج تحلیلی از CRT (فایل ۰۱) و SMC/ICT (فایل ۰۲)
- تطبیق و شناسایی ۷ ستاپ اصلی معاملاتی
- محاسبه دقیق سیستم امتیازدهی ۱۰۰ امتیازی (Setup Scoring Rubric)
- اعمال فیلتر سشن معاملاتی و اخبار اقتصادی
- تعیین حد ضرر ساختاری (SL) و اهداف سود سه‌گانه (TP1, TP2, TP3)
- صدور سیگنال تایید شده به همراه ریسک پیشنهادی برای تحویل به Risk Management Engine
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class SetupOpportunity:
    """خروجی نهایی فرصت معاملاتی تایید شده جهت ارسال به موتور ریسک"""
    opportunity_id: str
    symbol: str
    market: str
    direction: str  # 'BUY' or 'SELL'
    setup_name: str  # یکی از ۷ ستاپ اصلی
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward_ratio: float
    total_score: float
    score_breakdown: Dict[str, float]
    suggested_risk_pct: float
    is_counter_trend: bool
    status: str  # 'APPROVED', 'REJECTED'
    rejection_reason: Optional[str] = None
    confirmations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "market": self.market,
            "direction": self.direction,
            "setup_name": self.setup_name,
            "pricing": {
                "entry_price": round(self.entry_price, 5),
                "stop_loss": round(self.stop_loss, 5),
                "take_profit_1": round(self.take_profit_1, 5),
                "take_profit_2": round(self.take_profit_2, 5),
                "take_profit_3": round(self.take_profit_3, 5),
                "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            },
            "scoring": {
                "total_score": round(self.total_score, 1),
                "breakdown": self.score_breakdown,
                "suggested_risk_pct": self.suggested_risk_pct,
            },
            "is_counter_trend": self.is_counter_trend,
            "status": self.status,
            "rejection_reason": self.rejection_reason,
            "confirmations": self.confirmations,
            "timestamp": self.timestamp.isoformat(),
        }


class MasterSetupEngine:
    """
    موتور مرکزی ارزیابی، تطبیق و امتیازدهی ۷ ستاپ اصلی ARES
    """

    SETUP_NAMES = [
        "CRT Liquidity Sweep",
        "CRT + MSS + FVG",
        "Order Block Reversal",
        "FVG Trend Continuation",
        "Liquidity Sweep Reversal",
        "BOS + Retest",
        "Breakout + Retest",
    ]

    def __init__(self, min_rr_ratio: float = 1.5):
        self.min_rr_ratio = min_rr_ratio

    def calculate_score(
        self,
        crt_data: Dict,
        smc_data: Dict,
        session_valid: bool = True,
        in_news_window: bool = False,
    ) -> Tuple[float, Dict[str, float]]:
        """
        محاسبه سیستم امتیازدهی دقیق ۱۰۰ امتیازی طبق جدول سند ARES
        """
        breakdown = {
            "market_structure": 0.0,
            "liquidity_sweep": 0.0,
            "crt_range": 0.0,
            "mss_displacement": 0.0,
            "fvg_ob_retest": 0.0,
            "mtf_alignment": 0.0,
            "entry_confirmation": 0.0,
            "session_liquidity": 0.0,
        }

        # ۱. ساختار بازار (۱۵ امتیاز)
        trend = smc_data.get("trend_direction", "RANGING")
        if trend in ["BULLISH", "BEARISH"]:
            breakdown["market_structure"] += 10.0
        if smc_data.get("market_regime") == "TRENDING":
            breakdown["market_structure"] += 5.0

        # ۲. نقدینگی و Sweep (۱۵ امتیاز)
        sweep = crt_data.get("sweep", {})
        if sweep.get("status") == "VALID_SWEEP":
            breakdown["liquidity_sweep"] += 10.0
        if len(smc_data.get("liquidity", [])) > 0:
            breakdown["liquidity_sweep"] += 5.0

        # ۳. CRT و محدوده مرجع (۱۵ امتیاز)
        if sweep.get("closed_inside", False):
            breakdown["crt_range"] += 10.0
        ref = crt_data.get("reference_range", {})
        if ref.get("high", 0) > ref.get("low", 0):
            breakdown["crt_range"] += 5.0

        # ۴. MSS/BOS و Displacement (۱۵ امتیاز)
        ms = crt_data.get("market_structure", {})
        if ms.get("mss_status") == "CONFIRMED":
            breakdown["mss_displacement"] += 8.0
        if ms.get("displacement_status") == "CONFIRMED":
            breakdown["mss_displacement"] += 7.0

        # ۵. FVG / OB / Retest (۱۵ امتیاز)
        if len(crt_data.get("fvgs", [])) > 0:
            breakdown["fvg_ob_retest"] += 7.5
        if len(smc_data.get("order_blocks", [])) > 0:
            breakdown["fvg_ob_retest"] += 7.5

        # ۶. هماهنگی تایم‌فریم‌ها (۱۰ امتیاز)
        crt_dir = crt_data.get("direction", "NONE")
        if (crt_dir == "BUY" and trend == "BULLISH") or (crt_dir == "SELL" and trend == "BEARISH"):
            breakdown["mtf_alignment"] = 10.0
        elif crt_dir != "NONE":
            breakdown["mtf_alignment"] = 5.0

        # ۷. تایید ورود در تایم پایین (۱۰ امتیاز)
        if crt_data.get("retest_zone") is not None:
            breakdown["entry_confirmation"] = 10.0

        # ۸. سشن و نقدینگی (۵ امتیاز)
        if session_valid and not in_news_window:
            breakdown["session_liquidity"] = 5.0

        total_score = sum(breakdown.values())
        return total_score, breakdown

    def identify_primary_setup(self, crt_data: Dict, smc_data: Dict) -> str:
        has_crt_sweep = crt_data.get("sweep", {}).get("status") == "VALID_SWEEP"
        has_mss = crt_data.get("market_structure", {}).get("mss_status") == "CONFIRMED"
        has_fvg = len(crt_data.get("fvgs", [])) > 0
        has_ob = len(smc_data.get("order_blocks", [])) > 0
        has_bos = smc_data.get("structure_events", {}).get("last_bos") is not None

        if has_crt_sweep and has_mss and has_fvg:
            return "CRT + MSS + FVG"
        elif has_crt_sweep:
            return "CRT Liquidity Sweep"
        elif has_ob and has_mss:
            return "Order Block Reversal"
        elif has_bos and has_fvg:
            return "FVG Trend Continuation"
        elif has_crt_sweep and not has_fvg:
            return "Liquidity Sweep Reversal"
        elif has_bos:
            return "BOS + Retest"
        else:
            return "Breakout + Retest"

    def evaluate_opportunity(
        self,
        crt_result_dict: Dict,
        smc_result_dict: Dict,
        current_market_price: float,
        session_valid: bool = True,
        in_news_window: bool = False,
    ) -> SetupOpportunity:
        symbol = crt_result_dict.get("symbol", "UNKNOWN")
        market = crt_result_dict.get("market", "UNKNOWN")
        direction = crt_result_dict.get("direction", "NONE")
        opp_id = f"OPP_{symbol}_{uuid.uuid4().hex[:8]}"

        confirmations: List[str] = []

        # ۱. فیلتر خبر اقتصادی
        if in_news_window:
            return SetupOpportunity(
                opportunity_id=opp_id,
                symbol=symbol,
                market=market,
                direction=direction,
                setup_name="NONE",
                entry_price=current_market_price,
                stop_loss=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                take_profit_3=0.0,
                risk_reward_ratio=0.0,
                total_score=0.0,
                score_breakdown={},
                suggested_risk_pct=0.0,
                is_counter_trend=False,
                status="REJECTED",
                rejection_reason="ورود به معامله در بازه ۳۰ دقیقه قبل و بعد از خبر مهم (High Impact) ممنوع است.",
            )

        # ۲. محاسبه امتیاز فرصت (از ۱۰۰)
        total_score, breakdown = self.calculate_score(
            crt_result_dict, smc_result_dict, session_valid, in_news_window
        )

        # ۳. تشخیص ستاپ
        setup_name = self.identify_primary_setup(crt_result_dict, smc_result_dict)
        confirmations.append(f"الگوی ستاپ شناسایی شده: {setup_name}")

        # ۴. بررسی جهت و خلاف روند بودن
        trend = smc_result_dict.get("trend_direction", "RANGING")
        is_counter_trend = (
            (direction == "BUY" and trend == "BEARISH")
            or (direction == "SELL" and trend == "BULLISH")
        )

        if is_counter_trend:
            if total_score < 85.0:
                return SetupOpportunity(
                    opportunity_id=opp_id,
                    symbol=symbol,
                    market=market,
                    direction=direction,
                    setup_name=setup_name,
                    entry_price=current_market_price,
                    stop_loss=0.0,
                    take_profit_1=0.0,
                    take_profit_2=0.0,
                    take_profit_3=0.0,
                    risk_reward_ratio=0.0,
                    total_score=total_score,
                    score_breakdown=breakdown,
                    suggested_risk_pct=0.0,
                    is_counter_trend=True,
                    status="REJECTED",
                    rejection_reason=f"معامله خلاف جهت روند است و امتیاز ({total_score:.1f}) کمتر از حد نصاب ۸۵ می‌باشد.",
                )
            confirmations.append("معامله خلاف روند با نمره بالای ۸۵ و تایید کامل ساختار مجاز شناخته شد.")

        # ۵. قانون حد نصاب امتیاز: زیر ۶۰ معامله کلاً ممنوع
        if total_score < 60.0:
            return SetupOpportunity(
                opportunity_id=opp_id,
                symbol=symbol,
                market=market,
                direction=direction,
                setup_name=setup_name,
                entry_price=current_market_price,
                stop_loss=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                take_profit_3=0.0,
                risk_reward_ratio=0.0,
                total_score=total_score,
                score_breakdown=breakdown,
                suggested_risk_pct=0.0,
                is_counter_trend=is_counter_trend,
                status="REJECTED",
                rejection_reason=f"امتیاز ستاپ ({total_score:.1f}) کمتر از حد نصاب الزامی ۶۰ است.",
            )

        # ۶. تعیین درصد ریسک پیشنهادی بر اساس نمره
        if 60.0 <= total_score < 75.0:
            suggested_risk = 0.5
        elif 75.0 <= total_score < 85.0:
            suggested_risk = 1.0
        else:
            suggested_risk = 1.5

        # ۷. محاسبه دقیق نقطه ورود، حد ضرر (SL) و اهداف سود (TP1, TP2, TP3)
        retest_zone = crt_result_dict.get("retest_zone")
        ref_range = crt_result_dict.get("reference_range", {})

        if direction == "BUY":
            entry_price = float(retest_zone.get("entry_high", current_market_price)) if retest_zone else float(current_market_price)
            stop_loss = float(crt_result_dict.get("invalidation_price", entry_price * 0.99))
            risk_dist = entry_price - stop_loss
            if risk_dist <= 0:
                risk_dist = entry_price * 0.005
                stop_loss = entry_price - risk_dist

            tp1 = entry_price + (risk_dist * 1.5)
            tp2 = entry_price + (risk_dist * 2.5)
            tp3 = float(ref_range.get("high", entry_price + (risk_dist * 4.0)))

        elif direction == "SELL":
            entry_price = float(retest_zone.get("entry_low", current_market_price)) if retest_zone else float(current_market_price)
            stop_loss = float(crt_result_dict.get("invalidation_price", entry_price * 1.01))
            risk_dist = stop_loss - entry_price
            if risk_dist <= 0:
                risk_dist = entry_price * 0.005
                stop_loss = entry_price + risk_dist

            tp1 = entry_price - (risk_dist * 1.5)
            tp2 = entry_price - (risk_dist * 2.5)
            tp3 = float(ref_range.get("low", entry_price - (risk_dist * 4.0)))
        else:
            return SetupOpportunity(
                opportunity_id=opp_id,
                symbol=symbol,
                market=market,
                direction="NONE",
                setup_name=setup_name,
                entry_price=current_market_price,
                stop_loss=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                take_profit_3=0.0,
                risk_reward_ratio=0.0,
                total_score=total_score,
                score_breakdown=breakdown,
                suggested_risk_pct=0.0,
                is_counter_trend=is_counter_trend,
                status="REJECTED",
                rejection_reason="جهت قطعی BUY یا SELL توسط موتورهای پایه صادر نشده است.",
            )

        sl_distance = abs(entry_price - stop_loss)
        rr_ratio = (abs(tp1 - entry_price) / sl_distance) if sl_distance > 0 else 0.0

        if rr_ratio < self.min_rr_ratio:
            return SetupOpportunity(
                opportunity_id=opp_id,
                symbol=symbol,
                market=market,
                direction=direction,
                setup_name=setup_name,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit_1=tp1,
                take_profit_2=tp2,
                take_profit_3=tp3,
                risk_reward_ratio=rr_ratio,
                total_score=total_score,
                score_breakdown=breakdown,
                suggested_risk_pct=suggested_risk,
                is_counter_trend=is_counter_trend,
                status="REJECTED",
                rejection_reason=f"نسبت سود به زیان ({rr_ratio:.2f}) کمتر از حداقل مجاز ({self.min_rr_ratio}) است.",
            )

        confirmations.append(f"نسبت ریسک به ریوارد {rr_ratio:.2f} معتبر است.")
        confirmations.append(f"امتیاز ستاپ: {total_score:.1f} / 100 — ریسک پیشنهادی: {suggested_risk}%")

        return SetupOpportunity(
            opportunity_id=opp_id,
            symbol=symbol,
            market=market,
            direction=direction,
            setup_name=setup_name,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            risk_reward_ratio=rr_ratio,
            total_score=total_score,
            score_breakdown=breakdown,
            suggested_risk_pct=suggested_risk,
            is_counter_trend=is_counter_trend,
            status="APPROVED",
            confirmations=confirmations,
        )


if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ARES AI TRADING SYSTEM — TESTING MODULE 03: MASTER SETUP ENGINE")
    print("=" * 70)

    mock_crt_output = {
        "symbol": "BTCUSDT",
        "market": "CRYPTO_FUTURES",
        "direction": "BUY",
        "reference_range": {"high": 98000.0, "low": 94000.0, "midpoint": 96000.0},
        "sweep": {"status": "VALID_SWEEP", "penetration": 250.0, "closed_inside": True},
        "market_structure": {"mss_status": "CONFIRMED", "displacement_status": "CONFIRMED"},
        "fvgs": [{"id": "FVG_1", "top": 94500.0, "bottom": 94200.0}],
        "retest_zone": {"entry_high": 94500.0, "entry_low": 94200.0},
        "invalidation_price": 93750.0,
    }

    mock_smc_output = {
        "trend_direction": "BULLISH",
        "market_regime": "TRENDING",
        "structure_events": {"last_bos": {"type": "BULLISH_BOS", "broken_level": 97500.0}},
        "order_blocks": [{"id": "OB_1", "direction": "BULLISH"}],
        "liquidity": [{"id": "POOL_1", "type": "SSL", "level": 94000.0}],
    }

    engine = MasterSetupEngine(min_rr_ratio=1.5)
    opportunity = engine.evaluate_opportunity(
        crt_result_dict=mock_crt_output,
        smc_result_dict=mock_smc_output,
        current_market_price=94400.0,
        session_valid=True,
        in_news_window=False,
    )

    print("\n[خروجی فرصت معاملاتی تایید شده توسط Master Setup Engine]:")
    pprint.pprint(opportunity.to_dict())

    print("\n" + "=" * 70)
    if opportunity.status == "APPROVED":
        print(f"✅ تست فایل شماره ۳ با موفقیت انجام شد! ستاپ تایید شد (نمره: {opportunity.total_score}/100)")
        print(f"🎯 ریسک پیشنهادی به موتور مدیریت ریسک: {opportunity.suggested_risk_pct}%")
    else:
        print(f"⚠️ ستاپ رد شد. دلیل: {opportunity.rejection_reason}")
    print("=" * 70)