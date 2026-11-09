"""
================================================================================
ARES AI TRADING SYSTEM
FILE 01: CRT STRATEGY ENGINE (Candle Range Theory)
VERSION: 2.0 (PYTHON 3.12+ TIMEZONE COMPLIANT & MULTI-ASSET PRECISION)
================================================================================
ماموریت ماژول:
این ماژول وظیفه تحلیل ساختاری و ریاضی نظریه محدوده کندل (CRT) را بر عهده دارد.
این موتور به تنهایی معامله باز نمی کند، بلکه فرصت های معتبر CRT را شناسایی،
اعتبارسنجی و داده های استاندارد را برای ارسال به Master Setup Engine استخراج می کند.

اصول قطعی رعایت شده:
- Causal Swing Detection (جلوگیری ۱۰۰٪ از Look-ahead bias)
- تفکیک دقیق Liquidity Sweep از شکست واقعی بر اساس نفوذ مجاز و بسته‌شدن مجدد
- Multi-Timeframe Analysis (کندل مرجع HTF، سویپ MTF، تایید ورود LTF)
- ثبت تمام متغیرهای محدوده مرجع (High, Low, Open, Close, Midpoint)
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ReferenceRange:
    """اطلاعات و محدوده تغییرناپذیر کندل مرجع (Reference Candle)"""
    candle_id: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open_price: float
    high: float
    low: float
    close: float
    midpoint: float

    @classmethod
    def from_candle(cls, row: pd.Series, timeframe: str) -> "ReferenceRange":
        high = float(row["high"])
        low = float(row["low"])
        mid = (high + low) / 2.0
        return cls(
            candle_id=str(row.get("candle_id", uuid.uuid4().hex[:8])),
            timeframe=timeframe,
            open_time=pd.to_datetime(row["timestamp"]),
            close_time=pd.to_datetime(row.get("close_time", row["timestamp"])),
            open_price=float(row["open"]),
            high=high,
            low=low,
            close=float(row["close"]),
            midpoint=mid,
        )


@dataclass
class FVGZone:
    """مشخصات گپ ارزش منصفانه (Fair Value Gap)"""
    fvg_id: str
    direction: str  # 'BULLISH' or 'BEARISH'
    top: float
    bottom: float
    timeframe: str
    created_time: datetime
    is_mitigated: bool = False
    mitigated_time: Optional[datetime] = None


@dataclass
class CRTAnalysisResult:
    """خروجی استاندارد موتور CRT جهت ارسال به Master Setup Engine"""
    analysis_id: str
    symbol: str
    market: str
    direction: str  # 'BUY', 'SELL', 'NONE'
    timeframes_used: Dict[str, str]
    ref_high: float
    ref_low: float
    ref_mid: float
    sweep_status: str  # 'VALID_SWEEP', 'BREAKOUT', 'NONE'
    sweep_penetration: float
    closed_inside: bool
    mss_status: str  # 'CONFIRMED', 'NONE'
    mss_level: Optional[float]
    displacement_status: str  # 'CONFIRMED', 'WEAK', 'NONE'
    displacement_strength: float
    active_fvgs: List[Dict] = field(default_factory=list)
    retest_zone: Optional[Dict[str, float]] = None
    invalidation_price: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "NO_SETUP"  # 'VALID', 'PENDING', 'INVALID', 'NO_SETUP'
    confirmation_evidence: List[str] = field(default_factory=list)
    rejection_evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "market": self.market,
            "direction": self.direction,
            "timeframes_used": self.timeframes_used,
            "reference_range": {
                "high": round(self.ref_high, 5),
                "low": round(self.ref_low, 5),
                "midpoint": round(self.ref_mid, 5),
            },
            "sweep": {
                "status": self.sweep_status,
                "penetration": round(self.sweep_penetration, 5),
                "closed_inside": self.closed_inside,
            },
            "market_structure": {
                "mss_status": self.mss_status,
                "mss_level": round(self.mss_level, 5) if self.mss_level else None,
                "displacement_status": self.displacement_status,
                "displacement_strength": round(self.displacement_strength, 2),
            },
            "fvgs": self.active_fvgs,
            "retest_zone": self.retest_zone,
            "invalidation_price": round(self.invalidation_price, 5) if self.invalidation_price else None,
            "status": self.status,
            "confirmation_evidence": self.confirmation_evidence,
            "rejection_evidence": self.rejection_evidence,
            "timestamp": self.timestamp.isoformat(),
        }


class CRTStrategyEngine:
    """
    موتور مستقل استراتژی CRT
    مسئول ارزیابی کامل پرایس‌اکشن مبتنی بر رنج مرجع بدون هیچ‌گونه سوگیری یا خطای آینده‌نگری
    """

    def __init__(
        self,
        min_sweep_atr_mult: float = 0.05,
        max_sweep_atr_mult: float = 1.80,
        displacement_atr_mult: float = 1.20,
        displacement_body_ratio: float = 0.55,
        swing_lookback: int = 3,
    ):
        self.min_sweep_atr_mult = min_sweep_atr_mult
        self.max_sweep_atr_mult = max_sweep_atr_mult
        self.displacement_atr_mult = displacement_atr_mult
        self.displacement_body_ratio = displacement_body_ratio
        self.swing_lookback = swing_lookback

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"].shift(1)
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.bfill().fillna(1.0)

    def identify_reference_range(
        self, df_htf: pd.DataFrame, timeframe_label: str = "H1"
    ) -> Optional[ReferenceRange]:
        if df_htf is None or len(df_htf) < 2:
            return None
        closed_candle = df_htf.iloc[-2]
        return ReferenceRange.from_candle(closed_candle, timeframe=timeframe_label)

    def detect_swings_causal(
        self, df: pd.DataFrame
    ) -> Tuple[pd.Series, pd.Series]:
        n = self.swing_lookback
        swing_high = pd.Series(False, index=df.index)
        swing_low = pd.Series(False, index=df.index)

        if len(df) < (2 * n + 1):
            return swing_high, swing_low

        for i in range(n, len(df) - n):
            current_high = float(df["high"].iloc[i])
            current_low = float(df["low"].iloc[i])

            is_high = True
            for j in range(1, n + 1):
                if float(df["high"].iloc[i - j]) >= current_high or float(df["high"].iloc[i + j]) > current_high:
                    is_high = False
                    break
            if is_high:
                swing_high.iloc[i + n] = True

            is_low = True
            for j in range(1, n + 1):
                if float(df["low"].iloc[i - j]) <= current_low or float(df["low"].iloc[i + j]) < current_low:
                    is_low = False
                    break
            if is_low:
                swing_low.iloc[i + n] = True

        return swing_high, swing_low

    def detect_displacement(
        self, row: pd.Series, atr_value: float
    ) -> Tuple[bool, float]:
        if pd.isna(atr_value) or atr_value <= 0:
            return False, 0.0

        candle_range = float(row["high"] - row["low"])
        candle_body = abs(float(row["close"] - row["open"]))

        if candle_range <= 0:
            return False, 0.0

        body_ratio = candle_body / candle_range
        strength = candle_range / atr_value

        is_displacement = (
            strength >= self.displacement_atr_mult
            and body_ratio >= self.displacement_body_ratio
        )
        return is_displacement, float(strength)

    def detect_fvgs(
        self, df: pd.DataFrame, timeframe_label: str
    ) -> List[FVGZone]:
        fvgs: List[FVGZone] = []
        if df is None or len(df) < 3:
            return fvgs

        for i in range(2, len(df)):
            c1 = df.iloc[i - 2]
            c3 = df.iloc[i]

            if float(c3["low"]) > float(c1["high"]):
                fvg = FVGZone(
                    fvg_id=f"BULL_FVG_{i}_{uuid.uuid4().hex[:6]}",
                    direction="BULLISH",
                    top=float(c3["low"]),
                    bottom=float(c1["high"]),
                    timeframe=timeframe_label,
                    created_time=pd.to_datetime(df.iloc[i]["timestamp"]),
                )
                for k in range(i + 1, len(df)):
                    if float(df.iloc[k]["low"]) <= fvg.bottom:
                        fvg.is_mitigated = True
                        fvg.mitigated_time = pd.to_datetime(df.iloc[k]["timestamp"])
                        break
                if not fvg.is_mitigated:
                    fvgs.append(fvg)

            elif float(c3["high"]) < float(c1["low"]):
                fvg = FVGZone(
                    fvg_id=f"BEAR_FVG_{i}_{uuid.uuid4().hex[:6]}",
                    direction="BEARISH",
                    top=float(c1["low"]),
                    bottom=float(c3["high"]),
                    timeframe=timeframe_label,
                    created_time=pd.to_datetime(df.iloc[i]["timestamp"]),
                )
                for k in range(i + 1, len(df)):
                    if float(df.iloc[k]["high"]) >= fvg.top:
                        fvg.is_mitigated = True
                        fvg.mitigated_time = pd.to_datetime(df.iloc[k]["timestamp"])
                        break
                if not fvg.is_mitigated:
                    fvgs.append(fvg)

        return fvgs

    def evaluate_crt_setup(
        self,
        symbol: str,
        market: str,
        df_htf: pd.DataFrame,
        df_mtf: pd.DataFrame,
        df_ltf: pd.DataFrame,
        htf_label: str = "H1",
        mtf_label: str = "M15",
        ltf_label: str = "M5",
    ) -> CRTAnalysisResult:
        analysis_id = f"CRT_{symbol}_{uuid.uuid4().hex[:8]}"
        timeframes_used = {"HTF": htf_label, "MTF": mtf_label, "LTF": ltf_label}

        ref_range = self.identify_reference_range(df_htf, timeframe_label=htf_label)
        if ref_range is None or df_mtf is None or df_ltf is None or len(df_mtf) < 12 or len(df_ltf) < 12:
            return CRTAnalysisResult(
                analysis_id=analysis_id,
                symbol=symbol,
                market=market,
                direction="NONE",
                timeframes_used=timeframes_used,
                ref_high=0.0,
                ref_low=0.0,
                ref_mid=0.0,
                sweep_status="NONE",
                sweep_penetration=0.0,
                closed_inside=False,
                mss_status="NONE",
                mss_level=None,
                displacement_status="NONE",
                displacement_strength=0.0,
                status="NO_SETUP",
                rejection_evidence=["داده‌های کندلی جهت تحلیل کامل ستاپ کافی نیست."],
            )

        atr_series_mtf = self.calculate_atr(df_mtf)
        current_atr = float(atr_series_mtf.iloc[-1]) if not pd.isna(atr_series_mtf.iloc[-1]) else 1.0

        recent_mtf = df_mtf.tail(12)
        confirmations: List[str] = [f"کندل مرجع {htf_label} شناسایی شد."]
        rejections: List[str] = []

        bullish_sweep_detected = False
        bearish_sweep_detected = False
        sweep_penetration = 0.0
        closed_inside = False

        lowest_mtf = float(recent_mtf["low"].min())
        if lowest_mtf < ref_range.low:
            penetration = ref_range.low - lowest_mtf
            min_valid = self.min_sweep_atr_mult * current_atr
            max_valid = self.max_sweep_atr_mult * current_atr

            if min_valid <= penetration <= max_valid:
                last_closed_mtf = df_mtf.iloc[-2]
                if float(last_closed_mtf["close"]) > ref_range.low:
                    bullish_sweep_detected = True
                    closed_inside = True
                    sweep_penetration = float(penetration)
                    confirmations.append(f"سویپ موفقیت‌آمیز کف رنج ({ref_range.low:.4f})")
            elif penetration > max_valid:
                rejections.append("نفوذ به کف فراتر از سقف مجاز است (شکست ساختار نه Sweep).")

        highest_mtf = float(recent_mtf["high"].max())
        if highest_mtf > ref_range.high:
            penetration = highest_mtf - ref_range.high
            min_valid = self.min_sweep_atr_mult * current_atr
            max_valid = self.max_sweep_atr_mult * current_atr

            if min_valid <= penetration <= max_valid:
                last_closed_mtf = df_mtf.iloc[-2]
                if float(last_closed_mtf["close"]) < ref_range.high:
                    bearish_sweep_detected = True
                    closed_inside = True
                    sweep_penetration = float(penetration)
                    confirmations.append(f"سویپ موفقیت‌آمیز سقف رنج ({ref_range.high:.4f})")
            elif penetration > max_valid:
                rejections.append("نفوذ به سقف فراتر از سقف مجاز است (شکست ساختار نه Sweep).")

        direction = "NONE"
        if bullish_sweep_detected and not bearish_sweep_detected:
            direction = "BUY"
        elif bearish_sweep_detected and not bullish_sweep_detected:
            direction = "SELL"
        else:
            return CRTAnalysisResult(
                analysis_id=analysis_id,
                symbol=symbol,
                market=market,
                direction="NONE",
                timeframes_used=timeframes_used,
                ref_high=ref_range.high,
                ref_low=ref_range.low,
                ref_mid=ref_range.midpoint,
                sweep_status="NONE",
                sweep_penetration=0.0,
                closed_inside=False,
                mss_status="NONE",
                mss_level=None,
                displacement_status="NONE",
                displacement_strength=0.0,
                status="NO_SETUP",
                confirmation_evidence=confirmations,
                rejection_evidence=["هیچ سویپ معتبری در مرزهای کندل مرجع مشاهده نشد."],
            )

        last_candle = df_mtf.iloc[-2]
        is_disp, disp_strength = self.detect_displacement(last_candle, current_atr)
        displacement_status = "CONFIRMED" if is_disp else "WEAK"

        swing_highs_ltf, swing_lows_ltf = self.detect_swings_causal(df_ltf)
        mss_status = "NONE"
        mss_level = None

        if direction == "BUY":
            high_indices = np.where(swing_highs_ltf)[0]
            if len(high_indices) > 0:
                last_swing_idx = high_indices[-1]
                target_level = float(df_ltf.iloc[last_swing_idx]["high"])
                if float(df_ltf.iloc[-1]["close"]) > target_level:
                    mss_status = "CONFIRMED"
                    mss_level = target_level
                    confirmations.append(f"تغییر ساختار بازار (MSS صعودی) در سطح {target_level:.4f} تایید شد.")
        elif direction == "SELL":
            low_indices = np.where(swing_lows_ltf)[0]
            if len(low_indices) > 0:
                last_swing_idx = low_indices[-1]
                target_level = float(df_ltf.iloc[last_swing_idx]["low"])
                if float(df_ltf.iloc[-1]["close"]) < target_level:
                    mss_status = "CONFIRMED"
                    mss_level = target_level
                    confirmations.append(f"تغییر ساختار بازار (MSS نزولی) در سطح {target_level:.4f} تایید شد.")

        fvgs = self.detect_fvgs(df_mtf, timeframe_label=mtf_label)
        active_fvg_dicts = []
        retest_zone = None

        for fvg in fvgs:
            if direction == "BUY" and fvg.direction == "BULLISH":
                active_fvg_dicts.append({"id": fvg.fvg_id, "top": fvg.top, "bottom": fvg.bottom})
                if retest_zone is None:
                    retest_zone = {"entry_high": fvg.top, "entry_low": fvg.bottom}
            elif direction == "SELL" and fvg.direction == "BEARISH":
                active_fvg_dicts.append({"id": fvg.fvg_id, "top": fvg.top, "bottom": fvg.bottom})
                if retest_zone is None:
                    retest_zone = {"entry_high": fvg.top, "entry_low": fvg.bottom}

        invalidation_price = float(lowest_mtf) if direction == "BUY" else float(highest_mtf)

        is_valid = closed_inside and (mss_status == "CONFIRMED") and (displacement_status == "CONFIRMED")
        final_status = "VALID" if is_valid else ("PENDING" if closed_inside else "INVALID")

        return CRTAnalysisResult(
            analysis_id=analysis_id,
            symbol=symbol,
            market=market,
            direction=direction,
            timeframes_used=timeframes_used,
            ref_high=ref_range.high,
            ref_low=ref_range.low,
            ref_mid=ref_range.midpoint,
            sweep_status="VALID_SWEEP",
            sweep_penetration=sweep_penetration,
            closed_inside=closed_inside,
            mss_status=mss_status,
            mss_level=mss_level,
            displacement_status=displacement_status,
            displacement_strength=disp_strength,
            active_fvgs=active_fvg_dicts,
            retest_zone=retest_zone,
            invalidation_price=invalidation_price,
            status=final_status,
            confirmation_evidence=confirmations,
            rejection_evidence=rejections,
        )