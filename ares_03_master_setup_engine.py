"""
================================================================================
ARES AI TRADING SYSTEM
FILE 03: MASTER SETUP ENGINE
VERSION: 14.0 (LIVE MARKET ENTRY ANCHORING & STRICT SL/TP VALIDATION)
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


@dataclass
class SetupOpportunity:
    """خروجی نهایی فرصت معاملاتی تایید شده جهت ارسال به موتور ریسک"""
    opportunity_id: str
    symbol: str
    market: str
    direction: str  # 'BUY' or 'SELL'
    setup_name: str
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
    """موتور مرکزی ارزیابی، تطبیق و امتیازدهی ۷ ستاپ اصلی ARES"""

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

        trend = smc_data.get("trend_direction", "RANGING")
        if trend in ["BULLISH", "BEARISH"]:
            breakdown["market_structure"] += 10.0
        if smc_data.get("market_regime") == "TRENDING":
            breakdown["market_structure"] += 5.0

        sweep = crt_data.get("sweep", {})
        if sweep.get("status") == "VALID_SWEEP":
            breakdown["liquidity_sweep"] += 10.0
        if len(smc_data.get("liquidity", [])) > 0:
            breakdown["liquidity_sweep"] += 5.0

        if sweep.get("closed_inside", False):
            breakdown["crt_range"] += 10.0
        ref = crt_data.get("reference_range", {})
        if ref.get("high", 0) > ref.get("low", 0):
            breakdown["crt_range"] += 5.0

        ms = crt_data.get("market_structure", {})
        if ms.get("mss_status") == "CONFIRMED":
            breakdown["mss_displacement"] += 8.0
        if ms.get("displacement_status") == "CONFIRMED":
            breakdown["mss_displacement"] += 7.0

        if len(crt_data.get("fvgs", [])) > 0:
            breakdown["fvg_ob_retest"] += 7.5
        if len(smc_data.get("order_blocks", [])) > 0:
            breakdown["fvg_ob_retest"] += 7.5

        crt_dir = crt_data.get("direction", "NONE")
        if (crt_dir == "BUY" and trend == "BULLISH") or (crt_dir == "SELL" and trend == "BEARISH"):
            breakdown["mtf_alignment"] = 10.0
        elif crt_dir != "NONE":
            breakdown["mtf_alignment"] = 5.0

        if crt_data.get("retest_zone") is not None:
            breakdown["entry_confirmation"] = 10.0

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
                rejection_reason="ورود به معامله در بازه ۳۰ دقیقه قبل و بعد از خبر مهم ممنوع است.",
            )

        total_score, breakdown = self.calculate_score(
            crt_result_dict, smc_result_dict, session_valid, in_news_window
        )

        setup_name = self.identify_primary_setup(crt_result_dict, smc_result_dict)
        confirmations.append(f"الگوی ستاپ شناسایی شده: {setup_name}")

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

        if 60.0 <= total_score < 75.0:
            suggested_risk = 0.5
        elif 75.0 <= total_score < 85.0:
            suggested_risk = 1.0
        else:
            suggested_risk = 1.5

        # همیشه قیمت ورود برابر با قیمت لحظه‌ای بازار است تا سفارش Market در متاتریدر بدون خطای استاپ اجرا شود
        entry_price = float(current_market_price)
        ref_range = crt_result_dict.get("reference_range", {})
        inv_price = crt_result_dict.get("invalidation_price")

        if direction == "BUY":
            stop_loss = float(inv_price) if (inv_price and float(inv_price) < entry_price) else (entry_price * 0.996)
            risk_dist = entry_price - stop_loss
            if risk_dist <= (entry_price * 0.0003):
                risk_dist = entry_price * 0.0025
                stop_loss = entry_price - risk_dist

            tp1 = entry_price + (risk_dist * 1.5)
            tp2 = entry_price + (risk_dist * 2.5)
            ref_high = float(ref_range.get("high", 0.0))
            tp3 = ref_high if ref_high > tp2 else (entry_price + (risk_dist * 4.0))

        elif direction == "SELL":
            stop_loss = float(inv_price) if (inv_price and float(inv_price) > entry_price) else (entry_price * 1.004)
            risk_dist = stop_loss - entry_price
            if risk_dist <= (entry_price * 0.0003):
                risk_dist = entry_price * 0.0025
                stop_loss = entry_price + risk_dist

            tp1 = entry_price - (risk_dist * 1.5)
            tp2 = entry_price - (risk_dist * 2.5)
            ref_low = float(ref_range.get("low", 0.0))
            tp3 = ref_low if (0 < ref_low < tp2) else (entry_price - (risk_dist * 4.0))
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