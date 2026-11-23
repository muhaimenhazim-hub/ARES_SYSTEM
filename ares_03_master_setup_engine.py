"""
================================================================================
ARES AI TRADING SYSTEM
FILE 03: MASTER SETUP ENGINE
VERSION: 14.4 (FVG-ONLY CRT+MSS+FVG, DAILY BIAS SCORING & 1.1R/1.5R/2.0R TARGETS)
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
    daily_bias: str = "NEUTRAL"
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
            "daily_bias": self.daily_bias,
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
    """موتور مرکزی ارزیابی، تطبیق و امتیازدهی ستاپ تاییدشده ARES"""

    SETUP_NAMES = [
        "CRT + MSS + FVG",
    ]

    def __init__(self, min_rr_ratio: float = 1.5):
        self.min_rr_ratio = min_rr_ratio

    @staticmethod
    def _has_retest_confirmation(
        direction: str,
        current_market_price: float,
        crt_data: Dict,
        smc_data: Dict,
    ) -> Tuple[bool, Optional[Dict[str, float]]]:
        """بررسی اینکه قیمت واقعاً به یک ناحیه فعال FVG یا Order Block پولبک (Retest) کرده باشد"""
        price = float(current_market_price or 0.0)
        if price <= 0.0 or direction not in ("BUY", "SELL"):
            return False, None

        candidate_zones: List[Tuple[float, float]] = []

        for fvg in crt_data.get("fvgs", []) or []:
            if not isinstance(fvg, dict):
                continue
            top = float(fvg.get("top", 0.0) or 0.0)
            bottom = float(fvg.get("bottom", 0.0) or 0.0)
            if top > 0.0 and bottom > 0.0:
                candidate_zones.append((min(bottom, top), max(bottom, top)))

        expected_ob_dir = "BULLISH" if direction == "BUY" else "BEARISH"
        for ob in smc_data.get("order_blocks", []) or []:
            if not isinstance(ob, dict):
                continue
            if str(ob.get("direction", "")).upper() != expected_ob_dir:
                continue
            top = float(ob.get("top", 0.0) or 0.0)
            bottom = float(ob.get("bottom", 0.0) or 0.0)
            if top > 0.0 and bottom > 0.0:
                candidate_zones.append((min(bottom, top), max(bottom, top)))

        rz = crt_data.get("retest_zone")
        if isinstance(rz, dict):
            eh = float(rz.get("entry_high", 0.0) or 0.0)
            el = float(rz.get("entry_low", 0.0) or 0.0)
            if eh > 0.0 and el > 0.0:
                candidate_zones.append((min(el, eh), max(el, eh)))

        for z_low, z_high in candidate_zones:
            z_height = max(0.0, z_high - z_low)
            tol = max(z_height * 0.20, price * 0.0003)
            if (z_low - tol) <= price <= (z_high + tol):
                return True, {"zone_low": z_low, "zone_high": z_high}

        return False, None

    def calculate_score(
        self,
        crt_data: Dict,
        smc_data: Dict,
        session_valid: bool = True,
        in_news_window: bool = False,
        retest_confirmed: Optional[bool] = None,
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
        daily_bias = str(smc_data.get("daily_bias", "NEUTRAL")).upper()
        aligned_mtf = (crt_dir == "BUY" and trend == "BULLISH") or (crt_dir == "SELL" and trend == "BEARISH")
        aligned_bias = (crt_dir == "BUY" and daily_bias == "BULLISH") or (crt_dir == "SELL" and daily_bias == "BEARISH")
        counter_bias = (crt_dir == "BUY" and daily_bias == "BEARISH") or (crt_dir == "SELL" and daily_bias == "BULLISH")

        if crt_dir != "NONE":
            if aligned_mtf and aligned_bias:
                breakdown["mtf_alignment"] = 10.0
            elif aligned_mtf and daily_bias == "NEUTRAL":
                breakdown["mtf_alignment"] = 10.0
            elif aligned_bias:
                breakdown["mtf_alignment"] = 8.0
            elif not counter_bias:
                breakdown["mtf_alignment"] = 5.0
            elif aligned_mtf and counter_bias:
                breakdown["mtf_alignment"] = 2.0
            else:
                breakdown["mtf_alignment"] = 0.0

        has_retest = (
            retest_confirmed
            if retest_confirmed is not None
            else (crt_data.get("retest_zone") is not None)
        )
        if has_retest:
            breakdown["entry_confirmation"] = 10.0

        if session_valid and not in_news_window:
            breakdown["session_liquidity"] = 5.0

        total_score = sum(breakdown.values())
        return total_score, breakdown

    def identify_primary_setup(self, crt_data: Dict, smc_data: Dict) -> str:
        has_crt_sweep = crt_data.get("sweep", {}).get("status") == "VALID_SWEEP"
        has_mss = crt_data.get("market_structure", {}).get("mss_status") == "CONFIRMED"
        has_fvg = len(crt_data.get("fvgs", []) or []) > 0

        if has_crt_sweep and has_mss and has_fvg:
            return "CRT + MSS + FVG"
        return "NONE"

    def evaluate_opportunity(
        self,
        crt_result_dict: Dict,
        smc_result_dict: Dict,
        current_market_price: float,
        session_valid: bool = True,
        in_news_window: bool = False,
        atr: float = 0.0,
    ) -> SetupOpportunity:
        symbol = crt_result_dict.get("symbol", "UNKNOWN")
        market = crt_result_dict.get("market", "UNKNOWN")
        direction = crt_result_dict.get("direction", "NONE")
        daily_bias = str(smc_result_dict.get("daily_bias", "NEUTRAL")).upper()
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
                daily_bias=daily_bias,
                rejection_reason="ورود به معامله در بازه ۳۰ دقیقه قبل و بعد از خبر مهم ممنوع است.",
            )

        setup_name = self.identify_primary_setup(crt_result_dict, smc_result_dict)

        # گیت ۱: اجباری بودن تاییدیه کامل CRT شامل Sweep + بازگشت به رنج + MSS + Displacement
        crt_status = crt_result_dict.get("status", "NO_SETUP")
        sweep_info = crt_result_dict.get("sweep", {})
        ms_info = crt_result_dict.get("market_structure", {})
        has_full_crt = (
            direction in ("BUY", "SELL")
            and crt_status == "VALID"
            and sweep_info.get("status") == "VALID_SWEEP"
            and bool(sweep_info.get("closed_inside", False))
            and ms_info.get("mss_status") == "CONFIRMED"
            and ms_info.get("displacement_status") == "CONFIRMED"
        )
        if not has_full_crt:
            total_score, breakdown = self.calculate_score(
                crt_result_dict,
                smc_result_dict,
                session_valid,
                in_news_window,
                retest_confirmed=False,
            )
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
                is_counter_trend=False,
                status="REJECTED",
                daily_bias=daily_bias,
                rejection_reason="ستاپ هنوز تاییدیه کامل (Sweep + بازگشت به رنج + MSS + Displacement) را دریافت نکرده است.",
            )

        # گیت ۲: اجباری بودن وجود FVG فعال (حذف کامل معاملات ضعیف بدون FVG)
        active_fvgs = crt_result_dict.get("fvgs", []) or []
        if len(active_fvgs) == 0 or setup_name != "CRT + MSS + FVG":
            total_score, breakdown = self.calculate_score(
                crt_result_dict,
                smc_result_dict,
                session_valid,
                in_news_window,
                retest_confirmed=False,
            )
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
                total_score=total_score,
                score_breakdown=breakdown,
                suggested_risk_pct=0.0,
                is_counter_trend=False,
                status="REJECTED",
                daily_bias=daily_bias,
                rejection_reason="ستاپ فاقد FVG فعال است؛ طبق نتایج بک‌تست، ورود بدون FVG مجاز نیست.",
            )

        # گیت ۳: اجباری بودن پولبک (Retest) قیمت به ناحیه فعال FVG یا Order Block
        retest_ok, matched_zone = self._has_retest_confirmation(
            direction=direction,
            current_market_price=current_market_price,
            crt_data=crt_result_dict,
            smc_data=smc_result_dict,
        )
        total_score, breakdown = self.calculate_score(
            crt_result_dict,
            smc_result_dict,
            session_valid,
            in_news_window,
            retest_confirmed=retest_ok,
        )
        if not retest_ok or matched_zone is None:
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
                is_counter_trend=False,
                status="REJECTED",
                daily_bias=daily_bias,
                rejection_reason="تاییدیه اولیه کامل است؛ اما ربات منتظر پولبک (Retest) قیمت به ناحیه FVG یا Order Block است.",
            )

        confirmations.append(f"الگوی ستاپ شناسایی شده: {setup_name}")
        confirmations.append(
            f"پولبک (Retest) قیمت به ناحیه معتبر ({matched_zone['zone_low']:.5f} تا {matched_zone['zone_high']:.5f}) تایید شد."
        )

        trend = smc_result_dict.get("trend_direction", "RANGING")
        is_counter_trend = (
            (direction == "BUY" and trend == "BEARISH")
            or (direction == "SELL" and trend == "BULLISH")
        )
        is_counter_daily_bias = (
            (direction == "BUY" and daily_bias == "BEARISH")
            or (direction == "SELL" and daily_bias == "BULLISH")
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
                    daily_bias=daily_bias,
                    rejection_reason=f"معامله خلاف جهت روند است و امتیاز ({total_score:.1f}) کمتر از حد نصاب ۸۵ می‌باشد.",
                )
            confirmations.append("معامله خلاف روند با نمره بالای ۸۵ و تایید کامل ساختار مجاز شناخته شد.")

        if is_counter_daily_bias and total_score < 75.0:
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
                daily_bias=daily_bias,
                rejection_reason=f"معامله خلاف بایاس روزانه ({daily_bias}) و با امتیاز کمتر از حد نصاب ۷۵ ({total_score:.1f}) است.",
            )

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
                daily_bias=daily_bias,
                rejection_reason=f"امتیاز ستاپ ({total_score:.1f}) کمتر از حد نصاب الزامی ۶۰ است.",
            )

        if 60.0 <= total_score < 75.0:
            suggested_risk = 0.5
        elif 75.0 <= total_score < 85.0:
            suggested_risk = 1.0
        else:
            suggested_risk = 1.5

        if is_counter_daily_bias and total_score < 85.0:
            suggested_risk = min(suggested_risk, 0.5)
            confirmations.append(f"شرایط ضدبایاس روزانه ({daily_bias}) اعمال شد: ریسک به {suggested_risk}% محدود گردید.")

        # محاسبه قیمت ورود و SL بر پایه ساختار سویپ + ATR
        entry_price = float(current_market_price)
        inv_price = crt_result_dict.get("invalidation_price")
        eff_atr = float(atr or 0.0)
        min_sl_dist = max(0.5 * eff_atr, entry_price * 0.0005) if eff_atr > 0 else (entry_price * 0.0012)
        fallback_sl_dist = max(1.5 * eff_atr, entry_price * 0.0020) if eff_atr > 0 else (entry_price * 0.0020)

        if direction == "BUY":
            stop_loss = float(inv_price) if (inv_price and float(inv_price) < entry_price) else (entry_price - fallback_sl_dist)
            risk_dist = entry_price - stop_loss
            if risk_dist < min_sl_dist:
                risk_dist = min_sl_dist
                stop_loss = entry_price - risk_dist

            tp1 = entry_price + (risk_dist * 1.1)
            tp2 = entry_price + (risk_dist * 1.5)
            tp3 = entry_price + (risk_dist * 2.0)

        elif direction == "SELL":
            stop_loss = float(inv_price) if (inv_price and float(inv_price) > entry_price) else (entry_price + fallback_sl_dist)
            risk_dist = stop_loss - entry_price
            if risk_dist < min_sl_dist:
                risk_dist = min_sl_dist
                stop_loss = entry_price + risk_dist

            tp1 = entry_price - (risk_dist * 1.1)
            tp2 = entry_price - (risk_dist * 1.5)
            tp3 = entry_price - (risk_dist * 2.0)
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
                daily_bias=daily_bias,
                rejection_reason="جهت قطعی BUY یا SELL توسط موتورهای پایه صادر نشده است.",
            )

        sl_distance = abs(entry_price - stop_loss)
        rr_ratio = (abs(tp3 - entry_price) / sl_distance) if sl_distance > 0 else 0.0

        if (rr_ratio + 1e-6) < self.min_rr_ratio:
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
                daily_bias=daily_bias,
                rejection_reason=f"نسبت سود به زیان ({rr_ratio:.2f}) کمتر از حداقل مجاز ({self.min_rr_ratio}) است.",
            )

        confirmations.append(f"نسبت ریسک به ریوارد نهایی {rr_ratio:.2f} معتبر است (خروج پله‌ای 1.1R / 1.5R / 2.0R).")
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
            daily_bias=daily_bias,
            confirmations=confirmations,
        )