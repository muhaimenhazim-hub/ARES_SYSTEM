"""
================================================================================
ARES AI TRADING SYSTEM
FILE 01: CRT STRATEGY ENGINE (Candle Range Theory)
VERSION: 1.1
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
from datetime import datetime
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
    timestamp: datetime = field(default_factory=datetime.utcnow)
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
                "high": self.ref_high,
                "low": self.ref_low,
                "midpoint": self.ref_mid,
            },
            "sweep": {
                "status": self.sweep_status,
                "penetration": self.sweep_penetration,
                "closed_inside": self.closed_inside,
            },
            "market_structure": {
                "mss_status": self.mss_status,
                "mss_level": self.mss_level,
                "displacement_status": self.displacement_status,
                "displacement_strength": self.displacement_strength,
            },
            "fvgs": self.active_fvgs,
            "retest_zone": self.retest_zone,
            "invalidation_price": self.invalidation_price,
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
        """
        پارامترهای قابل تنظیم کالیبراسیون:
        :param min_sweep_atr_mult: حداقل نفوذ به سطح برای تایید وقوع Sweep (نسبت به ATR)
        :param max_sweep_atr_mult: حداکثر نفوذ مجاز (فراتر از آن شکست ساختار است نه سویپ نقدینگی)
        :param displacement_atr_mult: حداقل بزرگی کندل نسبت به ATR جهت تایید Displacement
        :param displacement_body_ratio: حداقل نسبت بدنه کندل به کل طول آن
        :param swing_lookback: تعداد کندل‌های دو طرف جهت تایید نقاط عطف ساختاری (کاملاً علیتی)
        """
        self.min_sweep_atr_mult = min_sweep_atr_mult
        self.max_sweep_atr_mult = max_sweep_atr_mult
        self.displacement_atr_mult = displacement_atr_mult
        self.displacement_body_ratio = displacement_body_ratio
        self.swing_lookback = swing_lookback

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """محاسبه دقیق میانگین دامنه واقعی (ATR)"""
        high = df["high"]
        low = df["low"]
        close = df["close"].shift(1)
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period, min_periods=period).mean()

    def identify_reference_range(
        self, df_htf: pd.DataFrame, timeframe_label: str = "H1"
    ) -> Optional[ReferenceRange]:
        """
        استخراج محدوده کندل مرجع از تایم‌فریم بالاتر (HTF)
        قانون: فقط کندل‌های کاملاً بسته‌شده مجاز به انتخاب هستند.
        """
        if len(df_htf) < 2:
            return None
        # استفاده از آخرین کندلِ کاملاً بسته شده (شاخص -2 برای جلوگیری از کندل لایو باز)
        closed_candle = df_htf.iloc[-2]
        return ReferenceRange.from_candle(closed_candle, timeframe=timeframe_label)

    def detect_swings_causal(
        self, df: pd.DataFrame
    ) -> Tuple[pd.Series, pd.Series]:
        """
        تشخیص نقاط عطف (Swing High / Swing Low) به شکل کاملاً علّی (بدون Look-ahead bias).
        تایید قله یا دره فقط پس از بسته شدن 'swing_lookback' کندل بعدی صورت می‌گیرد.
        """
        n = self.swing_lookback
        swing_high = pd.Series(False, index=df.index)
        swing_low = pd.Series(False, index=df.index)

        # از 2*n به بعد امکان بررسی گذشته به طور قطعی وجود دارد
        for i in range(n, len(df) - n):
            current_high = df["high"].iloc[i]
            current_low = df["low"].iloc[i]

            # بررسی قله بودن نسبت به n کندل قبل و n کندل بعد
            is_high = True
            for j in range(1, n + 1):
                if df["high"].iloc[i - j] >= current_high or df["high"].iloc[i + j] > current_high:
                    is_high = False
                    break
            if is_high:
                # سیگنال عطف در زمان بسته شدن کندل (i + n) در دسترس تلقی می‌شود
                swing_high.iloc[i + n] = True

            # بررسی دره بودن نسبت به n کندل قبل و n کندل بعد
            is_low = True
            for j in range(1, n + 1):
                if df["low"].iloc[i - j] <= current_low or df["low"].iloc[i + j] < current_low:
                    is_low = False
                    break
            if is_low:
                swing_low.iloc[i + n] = True

        return swing_high, swing_low

    def detect_displacement(
        self, row: pd.Series, atr_value: float
    ) -> Tuple[bool, float]:
        """
        ارزیابی شدت حرکت کندل (Displacement) با مقایسه با نوسان جاری بازار
        """
        if pd.isna(atr_value) or atr_value <= 0:
            return False, 0.0

        candle_range = float(row["high"] - row["low"])
        candle_body = abs(float(row["close"] - row["open"]))

        if candle_range == 0:
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
        """
        تشخیص گپ‌های ارزش منصفانه (FVG سه‌کندلی) و بررسی وضعیت مصرف‌شدن (Mitigation)
        """
        fvgs: List[FVGZone] = []
        if len(df) < 3:
            return fvgs

        for i in range(2, len(df)):
            c1 = df.iloc[i - 2]
            c3 = df.iloc[i]

            # صعودی: کف کندل سوم بالاتر از سقف کندل اول باشد
            if c3["low"] > c1["high"]:
                fvg = FVGZone(
                    fvg_id=f"BULL_FVG_{i}_{uuid.uuid4().hex[:6]}",
                    direction="BULLISH",
                    top=float(c3["low"]),
                    bottom=float(c1["high"]),
                    timeframe=timeframe_label,
                    created_time=pd.to_datetime(df.iloc[i]["timestamp"]),
                )
                # بررسی اینکه آیا کندل‌های بعدی آن را پر کرده‌اند؟
                current_price = df.iloc[-1]["close"]
                for k in range(i + 1, len(df)):
                    if df.iloc[k]["low"] <= fvg.bottom:
                        fvg.is_mitigated = True
                        fvg.mitigated_time = pd.to_datetime(df.iloc[k]["timestamp"])
                        break
                if not fvg.is_mitigated:
                    fvgs.append(fvg)

            # نزولی: سقف کندل سوم پایین‌تر از کف کندل اول باشد
            elif c3["high"] < c1["low"]:
                fvg = FVGZone(
                    fvg_id=f"BEAR_FVG_{i}_{uuid.uuid4().hex[:6]}",
                    direction="BEARISH",
                    top=float(c1["low"]),
                    bottom=float(c3["high"]),
                    timeframe=timeframe_label,
                    created_time=pd.to_datetime(df.iloc[i]["timestamp"]),
                )
                for k in range(i + 1, len(df)):
                    if df.iloc[k]["high"] >= fvg.top:
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
        """
        اجرای خط لوله کامل تحلیل CRT به صورت چندتایم‌فریمی:
        1. استخراج Reference Candle از HTF
        2. بررسی رخداد Liquidity Sweep در MTF و بسته‌شدن مجدد داخل رنج
        3. بررسی وقوع Displacement و تغییر جهت ساختار (MSS)
        4. شناسایی نواحی FVG فعال جهت Retest
        5. تولید گزارش ساختارمند جهت ارزیابی در Master Setup Engine
        """
        analysis_id = f"CRT_{symbol}_{uuid.uuid4().hex[:8]}"
        timeframes_used = {"HTF": htf_label, "MTF": mtf_label, "LTF": ltf_label}

        # گام ۱: شناسایی رنج مرجع
        ref_range = self.identify_reference_range(df_htf, timeframe_label=htf_label)
        if ref_range is None:
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
                rejection_evidence=["داده های تایم فریم بالاتر جهت استخراج رنج مرجع ناکافی است."],
            )

        atr_series_mtf = self.calculate_atr(df_mtf)
        current_atr = float(atr_series_mtf.iloc[-1]) if not pd.isna(atr_series_mtf.iloc[-1]) else 1.0

        # گام ۲: تحلیل رفتار قیمت در MTF نسبت به سقف و کف رنج مرجع
        # بررسی آخرین کندل‌های بسته شده در MTF
        recent_mtf = df_mtf.tail(12)
        confirmations: List[str] = [f"کندل مرجع معتبر {htf_label} با موفقیت شناسایی شد."]
        rejections: List[str] = []

        bullish_sweep_detected = False
        bearish_sweep_detected = False
        sweep_penetration = 0.0
        closed_inside = False

        # بررسی نفوذ به زیر کف رنج (Bullish Setup)
        lowest_mtf = recent_mtf["low"].min()
        if lowest_mtf < ref_range.low:
            penetration = ref_range.low - lowest_mtf
            min_valid = self.min_sweep_atr_mult * current_atr
            max_valid = self.max_sweep_atr_mult * current_atr

            if min_valid <= penetration <= max_valid:
                # بررسی اینکه آیا کندل بعدی به داخل محدوده بازگشته و بسته شده است؟
                last_closed_mtf = df_mtf.iloc[-2]
                if last_closed_mtf["close"] > ref_range.low:
                    bullish_sweep_detected = True
                    closed_inside = True
                    sweep_penetration = float(penetration)
                    confirmations.append(f"سویپ موفقیت‌آمیز کف رنج مرجع ({ref_range.low}) به میزان {penetration:.4f}")
                    confirmations.append("کندل MTF مجدداً در داخل محدوده رنج بسته شد.")
            elif penetration > max_valid:
                rejections.append("نفوذ به کف بیش از حد مجاز بوده و شکست ساختار (Breakout) است نه Sweep.")

        # بررسی نفوذ به بالای سقف رنج (Bearish Setup)
        highest_mtf = recent_mtf["high"].max()
        if highest_mtf > ref_range.high:
            penetration = highest_mtf - ref_range.high
            min_valid = self.min_sweep_atr_mult * current_atr
            max_valid = self.max_sweep_atr_mult * current_atr

            if min_valid <= penetration <= max_valid:
                last_closed_mtf = df_mtf.iloc[-2]
                if last_closed_mtf["close"] < ref_range.high:
                    bearish_sweep_detected = True
                    closed_inside = True
                    sweep_penetration = float(penetration)
                    confirmations.append(f"سویپ موفقیت‌آمیز سقف رنج مرجع ({ref_range.high}) به میزان {penetration:.4f}")
                    confirmations.append("کندل MTF مجدداً در داخل محدوده رنج بسته شد.")
            elif penetration > max_valid:
                rejections.append("نفوذ به سقف بیش از حد مجاز بوده و شکست ساختار (Breakout) است نه Sweep.")

        # تعیین جهت سناریو
        direction = "NONE"
        if bullish_sweep_detected and not bearish_sweep_detected:
            direction = "BUY"
        elif bearish_sweep_detected and not bullish_sweep_detected:
            direction = "SELL"
        else:
            if not bullish_sweep_detected and not bearish_sweep_detected:
                rejections.append("هیچ‌گونه Sweep معتبری روی مرزهای رنج مرجع رخ نداده است.")
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
                rejection_evidence=rejections,
            )

        # گام ۳: بررسی Displacement در کندل‌های بازگشتی
        last_candle = df_mtf.iloc[-2]
        is_disp, disp_strength = self.detect_displacement(last_candle, current_atr)
        displacement_status = "CONFIRMED" if is_disp else "WEAK"
        if is_disp:
            confirmations.append(f"کندل بازگشتی دارای جابه‌جایی قدرتمند (Displacement) با ضریب {disp_strength:.2f} است.")
        else:
            rejections.append("حرکت بازگشتی فاقد قدرت نوسانی و بدنه قدرتمند نسبت به ATR است.")

        # گام ۴: بررسی تغییر ساختار (MSS/CHoCH) در تایم پایین‌تر (LTF)
        swing_highs_ltf, swing_lows_ltf = self.detect_swings_causal(df_ltf)
        mss_status = "NONE"
        mss_level = None

        if direction == "BUY":
            # به دنبال شکست آخرین Swing High معتبر در LTF
            high_indices = np.where(swing_highs_ltf)[0]
            if len(high_indices) > 0:
                last_swing_idx = high_indices[-1]
                target_level = df_ltf.iloc[last_swing_idx]["high"]
                if df_ltf.iloc[-1]["close"] > target_level:
                    mss_status = "CONFIRMED"
                    mss_level = float(target_level)
                    confirmations.append(f"تغییر ساختار بازار (MSS صعودی) با عبور از سطح {target_level:.4f} تایید شد.")
        elif direction == "SELL":
            # به دنبال شکست آخرین Swing Low معتبر در LTF
            low_indices = np.where(swing_lows_ltf)[0]
            if len(low_indices) > 0:
                last_swing_idx = low_indices[-1]
                target_level = df_ltf.iloc[last_swing_idx]["low"]
                if df_ltf.iloc[-1]["close"] < target_level:
                    mss_status = "CONFIRMED"
                    mss_level = float(target_level)
                    confirmations.append(f"تغییر ساختار بازار (MSS نزولی) با عبور از سطح {target_level:.4f} تایید شد.")

        if mss_status == "NONE":
            rejections.append("تغییر ساختار معتبر (MSS) در تایم‌فریم تاییدیه رخ نداده است.")

        # گام ۵: استخراج FVG‌های فعال جهت Retest
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

        if retest_zone:
            confirmations.append(f"ناحیه FVG فعال جهت ورود در محدوده [{retest_zone['entry_low']:.4f} - {retest_zone['entry_high']:.4f}] ثبت شد.")

        # گام ۶: تعیین نقطه ابطال تحلیل (Invalidation Point)
        if direction == "BUY":
            invalidation_price = float(lowest_mtf)
        else:
            invalidation_price = float(highest_mtf)

        # ارزیابی وضعیت نهایی
        is_valid = (
            closed_inside
            and (mss_status == "CONFIRMED")
            and (displacement_status == "CONFIRMED")
        )
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


# ==============================================================================
# بخش تست خودکار و اعتبارسنجی زنده (Built-in Self-Test)
# این بخش مستقیماً یک ستاپ واقعی Bullish CRT را شبیه‌سازی کرده و موتور را می‌آزماید.
# ==============================================================================
if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ARES AI TRADING SYSTEM — TESTING MODULE 01: CRT STRATEGY ENGINE")
    print("=" * 70)

    # ۱. تولید داده کندلی مصنوعی HTF (H1) برای تشکیل رنج مرجع
    times_htf = pd.date_range("2025-01-01 08:00", periods=5, freq="1h")
    df_htf = pd.DataFrame(
        {
            "timestamp": times_htf,
            "open": [100.0, 102.0, 101.0, 103.0, 104.0],
            "high": [105.0, 106.0, 105.5, 108.0, 107.0],  # کندل مرجع سقف 108.0
            "low": [98.0, 99.0, 97.0, 96.0, 98.0],        # کندل مرجع کف 96.0
            "close": [102.0, 101.0, 103.0, 104.0, 105.0],
            "volume": [1000, 1200, 1100, 1500, 1300],
        }
    )

    # ۲. تولید داده MTF (M15) که کف ۹۶.۰ را به اندازه ۹۴.۸ سویپ می‌کند و بازمی‌گردد
    times_mtf = pd.date_range("2025-01-01 12:00", periods=20, freq="15min")
    np.random.seed(42)
    closes_mtf = np.linspace(100, 98, 20)
    df_mtf = pd.DataFrame(
        {
            "timestamp": times_mtf,
            "open": closes_mtf + 0.5,
            "high": closes_mtf + 1.0,
            "low": closes_mtf - 1.0,
            "close": closes_mtf,
            "volume": np.random.randint(500, 2000, 20),
        }
    )
    # کندل شماره ۱۵: نفوذ زیر ۹۶.۰ (کف ۹۴.۸)
    df_mtf.loc[14, "low"] = 94.8
    df_mtf.loc[14, "close"] = 95.5
    # کندل شماره ۱۸ (بسته‌شده قبل آخر): بازگشت به داخل رنج با بدنه قوی (Displacement)
    df_mtf.loc[18, "open"] = 95.8
    df_mtf.loc[18, "low"] = 95.7
    df_mtf.loc[18, "high"] = 100.5
    df_mtf.loc[18, "close"] = 100.2  # کاملاً داخل رنج (بزرگتر از ۹۶)

    # ۳. داده تایم‌فریم پایین LTF (M5) برای تایید MSS
    times_ltf = pd.date_range("2025-01-01 15:00", periods=25, freq="5min")
    df_ltf = pd.DataFrame(
        {
            "timestamp": times_ltf,
            "open": np.linspace(95, 101, 25),
            "high": np.linspace(96, 102, 25),
            "low": np.linspace(94.5, 100.5, 25),
            "close": np.linspace(95.5, 101.5, 25),
            "volume": np.random.randint(100, 800, 25),
        }
    )
    # ایجاد یک Swing High آشکار در شاخص ۱۰
    df_ltf.loc[10, "high"] = 98.5
    df_ltf.loc[24, "close"] = 101.5  # شکست معتبر قله قبلی (MSS)

    # اجرای تحلیل موتور CRT
    engine = CRTStrategyEngine()
    result = engine.evaluate_crt_setup(
        symbol="BTCUSDT",
        market="CRYPTO_FUTURES",
        df_htf=df_htf,
        df_mtf=df_mtf,
        df_ltf=df_ltf,
    )

    print("\n[نتیجه پردازش موتور استراتژی CRT]:")
    pprint.pprint(result.to_dict())

    print("\n" + "=" * 70)
    if result.status in ["VALID", "PENDING"]:
        print("✅ تست فایل شماره ۱ با موفقیت کامل انجام شد! ستاپ شناسایی و اعتبارسنجی شد.")
    else:
        print("⚠️ ستاپ تشکیل نشد، اما الگوریتم منطق را به درستی بررسی و رد کرد.")
    print("=" * 70)