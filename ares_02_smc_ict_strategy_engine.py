"""
================================================================================
ARES AI TRADING SYSTEM
FILE 02: SMC / ICT STRATEGY ENGINE (Smart Money Concepts & ICT)
VERSION: 2.0 (PYTHON 3.12+ TIMEZONE COMPLIANT & PANDAS 2.X COMPATIBLE)
================================================================================
ماموریت ماژول:
تحلیل جامع ساختار بازار، نقدینگی، مناطق عرضه و تقاضا، شکست‌های ساختاری (BOS, CHoCH, MSS)،
نواحی Premium/Discount و بلاک‌های سفارش (Order Blocks) به شکل علّی و بدون خطا.
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class SwingPoint:
    index: int
    timestamp: datetime
    price: float
    point_type: str  # 'HIGH' or 'LOW'
    level_type: str  # 'HH', 'HL', 'LH', 'LL'
    confirmed_at_index: int


@dataclass
class LiquidityPool:
    pool_id: str
    pool_type: str  # 'BSL', 'SSL', 'EQH', 'EQL'
    price_level: float
    tolerance: float
    is_swept: bool = False
    sweep_time: Optional[datetime] = None


@dataclass
class OrderBlock:
    ob_id: str
    direction: str  # 'BULLISH' یا 'BEARISH'
    top: float
    bottom: float
    timeframe: str
    created_time: datetime
    volume: float = 0.0
    is_mitigated: bool = False
    mitigated_time: Optional[datetime] = None


@dataclass
class SMCAnalysisResult:
    analysis_id: str
    symbol: str
    market: str
    trend_direction: str  # 'BULLISH', 'BEARISH', 'RANGING'
    timeframes_used: Dict[str, str]
    current_market_regime: str  # 'TRENDING', 'EQUILIBRIUM', 'VOLATILE'
    last_bos: Optional[Dict] = None
    last_choch: Optional[Dict] = None
    last_mss: Optional[Dict] = None
    active_order_blocks: List[Dict] = field(default_factory=list)
    active_fvgs: List[Dict] = field(default_factory=list)
    liquidity_pools: List[Dict] = field(default_factory=list)
    premium_discount_status: Dict = field(default_factory=dict)
    displacement_strength: float = 0.0
    status: str = "NEUTRAL"
    confirmation_evidence: List[str] = field(default_factory=list)
    rejection_evidence: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "analysis_id": self.analysis_id,
            "symbol": self.symbol,
            "market": self.market,
            "trend_direction": self.trend_direction,
            "market_regime": self.current_market_regime,
            "structure_events": {
                "last_bos": self.last_bos,
                "last_choch": self.last_choch,
                "last_mss": self.last_mss,
            },
            "order_blocks": self.active_order_blocks,
            "fvgs": self.active_fvgs,
            "liquidity": self.liquidity_pools,
            "pricing": self.premium_discount_status,
            "displacement_strength": round(self.displacement_strength, 2),
            "status": self.status,
            "confirmation_evidence": self.confirmation_evidence,
            "rejection_evidence": self.rejection_evidence,
            "timestamp": self.timestamp.isoformat(),
        }


class SMCICTStrategyEngine:
    def __init__(
        self,
        swing_lookback: int = 3,
        eqh_tolerance_pct: float = 0.0015,
        displacement_atr_mult: float = 1.25,
        displacement_body_ratio: float = 0.55,
    ):
        self.swing_lookback = swing_lookback
        self.eqh_tolerance_pct = eqh_tolerance_pct
        self.displacement_atr_mult = displacement_atr_mult
        self.displacement_body_ratio = displacement_body_ratio

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"].shift(1)
        tr = pd.concat([high - low, (high - close).abs(), (low - close).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window=period, min_periods=1).mean()
        return atr.bfill().fillna(1.0)

    def identify_swings(self, df: pd.DataFrame) -> List[SwingPoint]:
        swings: List[SwingPoint] = []
        n = self.swing_lookback
        if len(df) < (2 * n + 1):
            return swings

        for i in range(n, len(df) - n):
            current_high = float(df["high"].iloc[i])
            current_low = float(df["low"].iloc[i])

            is_high = True
            for j in range(1, n + 1):
                if float(df["high"].iloc[i - j]) >= current_high or float(df["high"].iloc[i + j]) > current_high:
                    is_high = False
                    break
            if is_high:
                level_type = "HIGH"
                if swings:
                    last_highs = [s for s in swings if s.point_type == "HIGH"]
                    if last_highs:
                        level_type = "HH" if current_high > last_highs[-1].price else "LH"
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=pd.to_datetime(df["timestamp"].iloc[i]),
                        price=current_high,
                        point_type="HIGH",
                        level_type=level_type,
                        confirmed_at_index=i + n,
                    )
                )

            is_low = True
            for j in range(1, n + 1):
                if float(df["low"].iloc[i - j]) <= current_low or float(df["low"].iloc[i + j]) < current_low:
                    is_low = False
                    break
            if is_low:
                level_type = "LOW"
                if swings:
                    last_lows = [s for s in swings if s.point_type == "LOW"]
                    if last_lows:
                        level_type = "LL" if current_low < last_lows[-1].price else "HL"
                swings.append(
                    SwingPoint(
                        index=i,
                        timestamp=pd.to_datetime(df["timestamp"].iloc[i]),
                        price=current_low,
                        point_type="LOW",
                        level_type=level_type,
                        confirmed_at_index=i + n,
                    )
                )

        swings.sort(key=lambda s: s.index)
        return swings

    def detect_liquidity_pools(self, swings: List[SwingPoint]) -> List[LiquidityPool]:
        pools: List[LiquidityPool] = []
        highs = [s for s in swings if s.point_type == "HIGH"]
        lows = [s for s in swings if s.point_type == "LOW"]

        for i in range(len(highs) - 1):
            diff = abs(highs[i].price - highs[i + 1].price)
            avg_price = (highs[i].price + highs[i + 1].price) / 2.0
            if avg_price > 0 and (diff / avg_price) <= self.eqh_tolerance_pct:
                pools.append(
                    LiquidityPool(
                        pool_id=f"EQH_{highs[i].index}_{uuid.uuid4().hex[:4]}",
                        pool_type="EQH",
                        price_level=avg_price,
                        tolerance=diff,
                    )
                )
            else:
                pools.append(
                    LiquidityPool(
                        pool_id=f"BSL_{highs[i].index}_{uuid.uuid4().hex[:4]}",
                        pool_type="BSL",
                        price_level=highs[i].price,
                        tolerance=0.0,
                    )
                )

        for i in range(len(lows) - 1):
            diff = abs(lows[i].price - lows[i + 1].price)
            avg_price = (lows[i].price + lows[i + 1].price) / 2.0
            if avg_price > 0 and (diff / avg_price) <= self.eqh_tolerance_pct:
                pools.append(
                    LiquidityPool(
                        pool_id=f"EQL_{lows[i].index}_{uuid.uuid4().hex[:4]}",
                        pool_type="EQL",
                        price_level=avg_price,
                        tolerance=diff,
                    )
                )
            else:
                pools.append(
                    LiquidityPool(
                        pool_id=f"SSL_{lows[i].index}_{uuid.uuid4().hex[:4]}",
                        pool_type="SSL",
                        price_level=lows[i].price,
                        tolerance=0.0,
                    )
                )

        return pools

    def detect_structure_events(
        self, df: pd.DataFrame, swings: List[SwingPoint]
    ) -> Tuple[Optional[Dict], Optional[Dict], Optional[Dict], str]:
        last_bos = None
        last_choch = None
        last_mss = None
        trend = "RANGING"

        if len(swings) < 3:
            return last_bos, last_choch, last_mss, trend

        highs = [s for s in swings if s.point_type == "HIGH"]
        lows = [s for s in swings if s.point_type == "LOW"]

        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price:
                trend = "BULLISH"
            elif highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price:
                trend = "BEARISH"

        last_closed = df.iloc[-2]
        current_close = float(last_closed["close"])

        if trend == "BULLISH" and highs:
            target_high = highs[-1].price
            if current_close > target_high:
                last_bos = {
                    "type": "BULLISH_BOS",
                    "broken_level": target_high,
                    "break_time": pd.to_datetime(last_closed["timestamp"]).isoformat(),
                }
        elif trend == "BEARISH" and lows:
            target_low = lows[-1].price
            if current_close < target_low:
                last_bos = {
                    "type": "BEARISH_BOS",
                    "broken_level": target_low,
                    "break_time": pd.to_datetime(last_closed["timestamp"]).isoformat(),
                }

        if trend == "BULLISH" and lows:
            target_low = lows[-1].price
            if current_close < target_low:
                last_choch = {
                    "type": "BEARISH_CHOCH",
                    "broken_level": target_low,
                    "break_time": pd.to_datetime(last_closed["timestamp"]).isoformat(),
                }
                last_mss = {
                    "type": "BEARISH_MSS",
                    "broken_level": target_low,
                    "shift_direction": "BEARISH",
                }
        elif trend == "BEARISH" and highs:
            target_high = highs[-1].price
            if current_close > target_high:
                last_choch = {
                    "type": "BULLISH_CHOCH",
                    "broken_level": target_high,
                    "break_time": pd.to_datetime(last_closed["timestamp"]).isoformat(),
                }
                last_mss = {
                    "type": "BULLISH_MSS",
                    "broken_level": target_high,
                    "shift_direction": "BULLISH",
                }

        return last_bos, last_choch, last_mss, trend

    def detect_order_blocks(
        self, df: pd.DataFrame, swings: List[SwingPoint], atr_series: pd.Series
    ) -> List[OrderBlock]:
        obs: List[OrderBlock] = []
        if len(df) < 5 or not swings:
            return obs

        for i in range(2, len(df) - 2):
            atr = float(atr_series.iloc[i])
            if pd.isna(atr) or atr <= 0:
                continue

            c_curr = df.iloc[i]
            c_next = df.iloc[i + 1]

            # Bullish OB
            if float(c_curr["close"]) < float(c_curr["open"]):
                c_range = float(c_next["high"] - c_next["low"])
                body = float(c_next["close"] - c_next["open"])
                body_ratio = body / (c_range + 1e-8)
                disp = c_range / atr

                if body > 0 and disp >= self.displacement_atr_mult and body_ratio >= self.displacement_body_ratio:
                    ob = OrderBlock(
                        ob_id=f"BULL_OB_{i}_{uuid.uuid4().hex[:4]}",
                        direction="BULLISH",
                        top=float(c_curr["high"]),
                        bottom=float(c_curr["low"]),
                        timeframe="MTF",
                        created_time=pd.to_datetime(c_curr["timestamp"]),
                    )
                    mitigated = False
                    for k in range(i + 2, len(df)):
                        if float(df.iloc[k]["low"]) <= ob.bottom:
                            mitigated = True
                            break
                    if not mitigated:
                        obs.append(ob)

            # Bearish OB
            elif float(c_curr["close"]) > float(c_curr["open"]):
                c_range = float(c_next["high"] - c_next["low"])
                body = float(c_next["open"] - c_next["close"])
                body_ratio = body / (c_range + 1e-8)
                disp = c_range / atr

                if body > 0 and disp >= self.displacement_atr_mult and body_ratio >= self.displacement_body_ratio:
                    ob = OrderBlock(
                        ob_id=f"BEAR_OB_{i}_{uuid.uuid4().hex[:4]}",
                        direction="BEARISH",
                        top=float(c_curr["high"]),
                        bottom=float(c_curr["low"]),
                        timeframe="MTF",
                        created_time=pd.to_datetime(c_curr["timestamp"]),
                    )
                    mitigated = False
                    for k in range(i + 2, len(df)):
                        if float(df.iloc[k]["high"]) >= ob.top:
                            mitigated = True
                            break
                    if not mitigated:
                        obs.append(ob)

        return obs

    def calculate_premium_discount(
        self, df: pd.DataFrame, swings: List[SwingPoint]
    ) -> Dict:
        if not swings:
            current_close = float(df.iloc[-1]["close"])
            return {
                "range_high": current_close,
                "range_low": current_close,
                "equilibrium": current_close,
                "current_zone": "EQUILIBRIUM",
            }

        highs = [s.price for s in swings if s.point_type == "HIGH"]
        lows = [s.price for s in swings if s.point_type == "LOW"]

        if not highs or not lows:
            return {"current_zone": "EQUILIBRIUM"}

        range_high = max(highs[-2:]) if len(highs) >= 2 else highs[-1]
        range_low = min(lows[-2:]) if len(lows) >= 2 else lows[-1]
        eq = (range_high + range_low) / 2.0
        current_price = float(df.iloc[-1]["close"])

        if current_price > eq:
            zone = "PREMIUM"
        elif current_price < eq:
            zone = "DISCOUNT"
        else:
            zone = "EQUILIBRIUM"

        return {
            "range_high": float(range_high),
            "range_low": float(range_low),
            "equilibrium": float(eq),
            "current_zone": zone,
            "current_price": current_price,
        }

    def analyze_market(
        self,
        symbol: str,
        market: str,
        df_mtf: pd.DataFrame,
        timeframe_label: str = "M15",
    ) -> SMCAnalysisResult:
        analysis_id = f"SMC_{symbol}_{uuid.uuid4().hex[:8]}"
        confirmations: List[str] = []
        rejections: List[str] = []

        if df_mtf is None or len(df_mtf) < 10:
            return SMCAnalysisResult(
                analysis_id=analysis_id,
                symbol=symbol,
                market=market,
                trend_direction="RANGING",
                timeframes_used={"MTF": timeframe_label},
                current_market_regime="EQUILIBRIUM",
                status="NEUTRAL",
                rejection_evidence=["داده‌های کندلی جهت تحلیل ساختار SMC کافی نیست."],
            )

        atr_series = self.calculate_atr(df_mtf)
        current_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 1.0

        swings = self.identify_swings(df_mtf)
        last_bos, last_choch, last_mss, trend = self.detect_structure_events(df_mtf, swings)
        confirmations.append(f"جهت ساختار کلی بازار: {trend}")

        if last_bos:
            confirmations.append(f"رویداد شکست ساختار (BOS) در سطح {last_bos['broken_level']} ثبت شد.")
        if last_choch:
            confirmations.append(f"هشدار تغییر رفتار (CHoCH) در سطح {last_choch['broken_level']} مشاهده شد.")

        pools = self.detect_liquidity_pools(swings)
        pool_dicts = [
            {"id": p.pool_id, "type": p.pool_type, "level": p.price_level}
            for p in pools
        ]

        obs = self.detect_order_blocks(df_mtf, swings, atr_series)
        ob_dicts = [
            {"id": ob.ob_id, "direction": ob.direction, "top": ob.top, "bottom": ob.bottom}
            for ob in obs
        ]

        pricing = self.calculate_premium_discount(df_mtf, swings)
        current_zone = pricing.get("current_zone", "EQUILIBRIUM")

        last_candle = df_mtf.iloc[-2]
        c_range = float(last_candle["high"] - last_candle["low"])
        disp_strength = float(c_range / current_atr) if current_atr > 0 else 0.0

        status = "NEUTRAL"
        if trend == "BULLISH" and current_zone == "DISCOUNT" and any(ob["direction"] == "BULLISH" for ob in ob_dicts):
            status = "BULLISH_OPPORTUNITY"
            confirmations.append("فرصت خرید معتبر: روند صعودی، قیمت در دیسکانت و اردربلاک صعودی فعال است.")
        elif trend == "BEARISH" and current_zone == "PREMIUM" and any(ob["direction"] == "BEARISH" for ob in ob_dicts):
            status = "BEARISH_OPPORTUNITY"
            confirmations.append("فرصت فروش معتبر: روند نزولی، قیمت در پریمیوم و اردربلاک نزولی فعال است.")
        else:
            rejections.append("شرایط هماهنگی روند و موقعیت قیمت در ناحیه تخفیف/گران‌قیمت مهیا نیست.")

        return SMCAnalysisResult(
            analysis_id=analysis_id,
            symbol=symbol,
            market=market,
            trend_direction=trend,
            timeframes_used={"MTF": timeframe_label},
            current_market_regime="TRENDING" if trend != "RANGING" else "EQUILIBRIUM",
            last_bos=last_bos,
            last_choch=last_choch,
            last_mss=last_mss,
            active_order_blocks=ob_dicts,
            active_fvgs=[],
            liquidity_pools=pool_dicts,
            premium_discount_status=pricing,
            displacement_strength=disp_strength,
            status=status,
            confirmation_evidence=confirmations,
            rejection_evidence=rejections,
        )