"""
================================================================================
ARES AI TRADING SYSTEM
FILE 04: TRADE & POSITION MANAGEMENT ENGINE
VERSION: 14.2 (1.0R BREAK-EVEN, 1.1R/1.5R/2.0R 30/30/40 EXITS & 0.01 LOT GUARD)
================================================================================
"""

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(Enum):
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"


class ExecutionMode(Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


@dataclass
class PartialExitRecord:
    """ثبت جزئیات خروج پله‌ای"""
    exit_id: str
    target_name: str
    exit_price: float
    closed_volume: float
    realized_pnl: float
    fee_paid: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ManagedPosition:
    """ساختار داده پوزیشن فعال و تحت مدیریت ARES با پشتیبانی از تیکت متاتریدر ۵"""
    position_id: str
    symbol: str
    market: str
    side: OrderSide
    entry_price: float
    initial_volume: float
    current_volume: float
    stop_loss: float
    initial_stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    risk_amount_usd: float
    user_id: str = "default"
    mt5_ticket: int = 0
    setup_name: str = ""
    setup_score: float = 0.0
    daily_bias: str = ""
    session_name: str = ""
    is_break_even: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    status: PositionStatus = PositionStatus.OPEN
    partial_exits: List[PartialExitRecord] = field(default_factory=list)
    realized_pnl: float = 0.0
    floating_pnl: float = 0.0
    total_fees_paid: float = 0.0
    open_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    close_time: Optional[datetime] = None
    exit_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        display_pnl = self.realized_pnl + (self.floating_pnl if self.status == PositionStatus.OPEN else 0.0)
        return {
            "position_id": self.position_id,
            "user_id": self.user_id,
            "mt5_ticket": self.mt5_ticket,
            "symbol": self.symbol,
            "market": self.market,
            "side": self.side.value,
            "entry_price": round(self.entry_price, 5),
            "initial_volume": round(self.initial_volume, 6),
            "current_volume": round(self.current_volume, 6),
            "stop_loss": round(self.stop_loss, 5),
            "initial_stop_loss": round(self.initial_stop_loss, 5),
            "targets": {
                "tp1": round(self.tp1, 5),
                "tp2": round(self.tp2, 5),
                "tp3": round(self.tp3, 5),
            },
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "setup_name": self.setup_name,
            "setup_score": self.setup_score,
            "daily_bias": self.daily_bias,
            "session_name": self.session_name,
            "is_break_even": self.is_break_even,
            "status": self.status.value,
            "realized_pnl": round(display_pnl, 2),
            "total_fees_paid": round(self.total_fees_paid, 4),
            "partial_exits_count": len(self.partial_exits),
            "exit_reason": self.exit_reason,
            "open_time": self.open_time.isoformat() if isinstance(self.open_time, datetime) else str(self.open_time),
            "close_time": self.close_time.isoformat() if isinstance(self.close_time, datetime) else self.close_time,
        }


class TradePositionManagementEngine:
    """موتور مستقل مدیریت معاملات و پوزیشن‌ها"""

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.LIVE,
        tp1_ratio: float = 0.30,
        tp2_ratio: float = 0.30,
        tp3_ratio: float = 0.40,
        taker_fee_pct: float = 0.0005,
    ):
        self.mode = mode
        self.tp1_ratio = tp1_ratio
        self.tp2_ratio = tp2_ratio
        self.tp3_ratio = tp3_ratio
        self.taker_fee_pct = taker_fee_pct
        self.open_positions: Dict[str, ManagedPosition] = {}
        self.trade_history: List[ManagedPosition] = []

    @staticmethod
    def calculate_partial_close_volume(
        initial_volume: float,
        current_volume: float,
        target_cum_ratio: float,
        min_volume: float = 0.01,
        volume_step: float = 0.01,
        is_forex_or_indices: bool = True,
    ) -> float:
        """محاسبه امن حجم خروج پله‌ای با رعایت حداقل حجم بروکر (0.01) و حفظ باقی‌مانده برای تارگت نهایی"""
        init_v = float(initial_volume or 0.0)
        cur_v = float(current_volume or 0.0)
        if init_v <= 0.0 or cur_v <= 0.0:
            return 0.0

        if not is_forex_or_indices:
            desired_remaining = max(0.0, init_v * max(0.0, 1.0 - target_cum_ratio))
            raw_close = max(0.0, cur_v - desired_remaining)
            return min(cur_v, round(raw_close, 6))

        if cur_v <= (min_volume + 1e-9):
            return 0.0

        desired_remaining = init_v * max(0.0, 1.0 - target_cum_ratio)
        raw_close = cur_v - desired_remaining
        if raw_close <= 0.0:
            return 0.0

        step = volume_step if volume_step > 0 else 0.01
        floored = math.floor((raw_close / step) + 1e-9) * step
        floored = round(floored, 4)

        if floored < min_volume:
            return 0.0

        remaining_after = round(cur_v - floored, 4)
        if remaining_after < (min_volume - 1e-9):
            max_safe_close = math.floor(((cur_v - min_volume) / step) + 1e-9) * step
            max_safe_close = round(max_safe_close, 4)
            if max_safe_close < min_volume:
                return 0.0
            floored = max_safe_close

        return floored

    def restore_position_from_db(self, row: Dict[str, Any]):
        """بازیابی پوزیشن باز از دیتابیس هنگام شروع مجدد برنامه با حفظ زمان واقعی بازشدن"""
        pos_id = str(row["trade_id"])
        if pos_id in self.open_positions:
            return
        side = OrderSide.BUY if str(row.get("side", "BUY")).upper() == "BUY" else OrderSide.SELL

        raw_opened = row.get("opened_at")
        parsed_open_time = datetime.now(timezone.utc)
        if isinstance(raw_opened, datetime):
            parsed_open_time = raw_opened
        elif isinstance(raw_opened, str) and raw_opened.strip():
            try:
                parsed_open_time = datetime.fromisoformat(raw_opened.strip().replace("Z", "+00:00"))
            except Exception:
                pass

        init_vol = float(row.get("initial_volume", row["current_volume"]))
        cur_vol = float(row["current_volume"])
        tp1_hit = bool(init_vol > 0 and cur_vol <= (init_vol * 0.75 + 1e-9))
        tp2_hit = bool(init_vol > 0 and cur_vol <= (init_vol * 0.45 + 1e-9))

        pos = ManagedPosition(
            position_id=pos_id,
            user_id=str(row.get("user_id", "default")),
            mt5_ticket=int(row.get("mt5_ticket", 0)),
            symbol=str(row["symbol"]),
            market=str(row.get("market", "FOREX_OR_INDICES")),
            side=side,
            entry_price=float(row["entry_price"]),
            initial_volume=init_vol,
            current_volume=cur_vol,
            stop_loss=float(row["stop_loss"]),
            initial_stop_loss=float(row.get("initial_stop_loss", row["stop_loss"])),
            tp1=float(row.get("tp1", 0.0)),
            tp2=float(row.get("tp2", 0.0)),
            tp3=float(row.get("tp3", 0.0)),
            risk_amount_usd=float(row.get("risk_amount_usd", 0.0)),
            setup_name=str(row.get("setup_name", "") or ""),
            setup_score=float(row.get("setup_score", 0.0) or 0.0),
            daily_bias=str(row.get("daily_bias", "") or ""),
            session_name=str(row.get("session_name", "") or ""),
            is_break_even=bool(row.get("is_break_even", 0)),
            tp1_hit=tp1_hit,
            tp2_hit=tp2_hit,
            realized_pnl=float(row.get("realized_pnl", 0.0)),
            total_fees_paid=float(row.get("total_fees", 0.0)),
            open_time=parsed_open_time,
        )
        self.open_positions[pos_id] = pos

    def open_position(
        self,
        symbol: str,
        market: str,
        side_str: str,
        entry_price: float,
        stop_loss: float,
        tp1: float,
        tp2: float,
        tp3: float,
        allocated_volume: float,
        risk_usd: float,
        user_id: str = "default",
        mt5_ticket: int = 0,
        setup_name: str = "",
        setup_score: float = 0.0,
        daily_bias: str = "",
        session_name: str = "",
    ) -> Tuple[bool, Optional[ManagedPosition], str]:
        for pos in self.open_positions.values():
            if pos.symbol == symbol and pos.user_id == user_id:
                return False, None, f"خطای رد سفارش: پوزیشن باز روی نماد {symbol} برای کاربر وجود دارد."

        side = OrderSide.BUY if side_str.upper() == "BUY" else OrderSide.SELL
        if side == OrderSide.BUY and stop_loss >= entry_price:
            return False, None, "خطا: برای معامله BUY حد ضرر باید زیر قیمت ورود باشد."
        if side == OrderSide.SELL and stop_loss <= entry_price:
            return False, None, "خطا: برای معامله SELL حد ضرر باید بالای قیمت ورود باشد."

        entry_fee = entry_price * allocated_volume * self.taker_fee_pct

        pos_id = f"POS_{symbol.replace(' ', '')}_{uuid.uuid4().hex[:8]}"
        new_pos = ManagedPosition(
            position_id=pos_id,
            user_id=user_id,
            mt5_ticket=mt5_ticket,
            symbol=symbol,
            market=market,
            side=side,
            entry_price=entry_price,
            initial_volume=allocated_volume,
            current_volume=allocated_volume,
            stop_loss=stop_loss,
            initial_stop_loss=stop_loss,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            risk_amount_usd=risk_usd,
            setup_name=setup_name,
            setup_score=setup_score,
            daily_bias=daily_bias,
            session_name=session_name,
            total_fees_paid=entry_fee,
        )

        self.open_positions[pos_id] = new_pos
        return True, new_pos, f"پوزیشن {pos_id} با موفقیت در حالت {self.mode.value} ایجاد شد."

    def update_position_on_price_tick(
        self,
        position_id: str,
        current_high: float,
        current_low: float,
        current_close: float,
        contract_size: float = 1.0,
        min_volume: float = 0.01,
        volume_step: float = 0.01,
    ) -> Dict[str, Any]:
        if position_id not in self.open_positions:
            return {"status": "NOT_FOUND"}

        pos = self.open_positions[position_id]
        events: List[str] = []
        is_fx_idx = pos.market != "CRYPTO_FUTURES"

        price_diff = (current_close - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - current_close)
        pos.floating_pnl = price_diff * pos.current_volume * contract_size

        # ۱. بررسی برخورد با حد ضرر (Stop Loss)
        if pos.stop_loss > 0:
            sl_hit = False
            sl_exit_price = pos.stop_loss

            if pos.side == OrderSide.BUY and current_low <= pos.stop_loss:
                sl_hit = True
            elif pos.side == OrderSide.SELL and current_high >= pos.stop_loss:
                sl_hit = True

            if sl_hit:
                loss_per_unit = (sl_exit_price - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - sl_exit_price)
                exit_fee = sl_exit_price * pos.current_volume * self.taker_fee_pct
                pos.realized_pnl += (loss_per_unit * pos.current_volume * contract_size) - exit_fee
                pos.floating_pnl = 0.0
                pos.total_fees_paid += exit_fee
                pos.current_volume = 0.0
                pos.status = PositionStatus.CLOSED
                pos.close_time = datetime.now(timezone.utc)
                pos.exit_reason = "STOP_LOSS_HIT" if not pos.is_break_even else "BREAK_EVEN_STOP_HIT"

                self.trade_history.append(pos)
                del self.open_positions[position_id]
                return {
                    "status": "CLOSED",
                    "reason": pos.exit_reason,
                    "position": pos.to_dict(),
                }

        # ۲. ریسک‌فری قطعی در ریوارد ۱.۰ (1.0R)
        risk_dist = abs(pos.entry_price - pos.initial_stop_loss)
        if risk_dist > 0 and not pos.is_break_even:
            be_trigger = (pos.entry_price + risk_dist) if pos.side == OrderSide.BUY else (pos.entry_price - risk_dist)
            be_reached = (pos.side == OrderSide.BUY and current_high >= be_trigger) or (
                pos.side == OrderSide.SELL and current_low <= be_trigger
            )
            if be_reached:
                fee_buffer = (
                    pos.entry_price * (self.taker_fee_pct * 2)
                    if not is_fx_idx
                    else min(risk_dist * 0.05, pos.entry_price * 0.0005)
                )
                pos.stop_loss = (
                    (pos.entry_price + fee_buffer)
                    if pos.side == OrderSide.BUY
                    else (pos.entry_price - fee_buffer)
                )
                pos.is_break_even = True
                events.append("ریوارد ۱.۰ (1.0R) محقق شد — حد ضرر به نقطه سر به سر (Break-Even) منتقل شد.")

        # ۳. پله اول TP1 (1.1R -> بستن ۳۰٪ حجم اولیه با محافظت 0.01)
        if pos.tp1 > 0 and not pos.tp1_hit:
            tp1_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp1) or (
                pos.side == OrderSide.SELL and current_low <= pos.tp1
            )
            if tp1_reached:
                pos.tp1_hit = True
                close_vol = self.calculate_partial_close_volume(
                    initial_volume=pos.initial_volume,
                    current_volume=pos.current_volume,
                    target_cum_ratio=self.tp1_ratio,
                    min_volume=min_volume,
                    volume_step=volume_step,
                    is_forex_or_indices=is_fx_idx,
                )
                if close_vol > 0:
                    pnl = ((pos.tp1 - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp1)) * close_vol * contract_size
                    fee = pos.tp1 * close_vol * self.taker_fee_pct
                    net_pnl = pnl - fee

                    pos.current_volume = max(0.0, round(pos.current_volume - close_vol, 6))
                    pos.realized_pnl += net_pnl
                    pos.total_fees_paid += fee
                    pos.partial_exits.append(
                        PartialExitRecord(
                            exit_id=uuid.uuid4().hex[:6],
                            target_name="TP1",
                            exit_price=pos.tp1,
                            closed_volume=close_vol,
                            realized_pnl=net_pnl,
                            fee_paid=fee,
                        )
                    )
                    events.append("TP1 (1.1R) محقق شد (۳۰٪ خروج پله‌ای).")
                else:
                    events.append("TP1 (1.1R) لمس شد — به دلیل حداقل حجم 0.01 پوزیشن با Break-Even حفظ شد.")

        # ۴. پله دوم TP2 (1.5R -> بستن ۳۰٪ حجم اولیه + تریلینگ استاپ به TP1)
        if pos.tp2 > 0 and pos.tp1_hit and not pos.tp2_hit:
            tp2_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp2) or (
                pos.side == OrderSide.SELL and current_low <= pos.tp2
            )
            if tp2_reached:
                pos.tp2_hit = True
                close_vol = self.calculate_partial_close_volume(
                    initial_volume=pos.initial_volume,
                    current_volume=pos.current_volume,
                    target_cum_ratio=(self.tp1_ratio + self.tp2_ratio),
                    min_volume=min_volume,
                    volume_step=volume_step,
                    is_forex_or_indices=is_fx_idx,
                )
                if close_vol > 0:
                    pnl = ((pos.tp2 - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp2)) * close_vol * contract_size
                    fee = pos.tp2 * close_vol * self.taker_fee_pct
                    net_pnl = pnl - fee

                    pos.current_volume = max(0.0, round(pos.current_volume - close_vol, 6))
                    pos.realized_pnl += net_pnl
                    pos.total_fees_paid += fee
                    pos.partial_exits.append(
                        PartialExitRecord(
                            exit_id=uuid.uuid4().hex[:6],
                            target_name="TP2",
                            exit_price=pos.tp2,
                            closed_volume=close_vol,
                            realized_pnl=net_pnl,
                            fee_paid=fee,
                        )
                    )
                if pos.tp1 > 0:
                    pos.stop_loss = pos.tp1
                events.append("TP2 (1.5R) محقق شد (۳۰٪ خروج پله‌ای) — تریلینگ استاپ به سطح TP1 ارتقا یافت.")

        # ۵. پله نهایی TP3 (2.0R -> بستن ۴۰٪ باقیمانده / تمام حجم باقیمانده)
        if pos.tp3 > 0 and pos.tp2_hit and not pos.tp3_hit:
            tp3_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp3) or (
                pos.side == OrderSide.SELL and current_low <= pos.tp3
            )
            if tp3_reached:
                pos.tp3_hit = True
                close_vol = pos.current_volume
                pnl = ((pos.tp3 - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp3)) * close_vol * contract_size
                fee = pos.tp3 * close_vol * self.taker_fee_pct
                net_pnl = pnl - fee

                pos.current_volume = 0.0
                pos.realized_pnl += net_pnl
                pos.floating_pnl = 0.0
                pos.total_fees_paid += fee
                pos.status = PositionStatus.CLOSED
                pos.close_time = datetime.now(timezone.utc)
                pos.exit_reason = "FULL_TAKE_PROFIT_TP3"
                pos.partial_exits.append(
                    PartialExitRecord(
                        exit_id=uuid.uuid4().hex[:6],
                        target_name="TP3",
                        exit_price=pos.tp3,
                        closed_volume=close_vol,
                        realized_pnl=net_pnl,
                        fee_paid=fee,
                    )
                )
                events.append("TP3 (2.0R) محقق شد (۴۰٪ پایانی) — معامله با سود کامل بسته شد.")

                self.trade_history.append(pos)
                del self.open_positions[position_id]
                return {
                    "status": "CLOSED",
                    "reason": "FULL_TAKE_PROFIT",
                    "events": events,
                    "position": pos.to_dict(),
                }

        return {
            "status": "OPEN",
            "current_volume": pos.current_volume,
            "events": events,
            "position": pos.to_dict(),
        }

    def emergency_close_all(self, reason: str = "EMERGENCY_STOP") -> List[Dict[str, Any]]:
        closed_reports = []
        for pos_id, pos in list(self.open_positions.items()):
            pos.status = PositionStatus.CLOSED
            pos.close_time = datetime.now(timezone.utc)
            pos.exit_reason = reason
            self.trade_history.append(pos)
            closed_reports.append(pos.to_dict())
            del self.open_positions[pos_id]
        return closed_reports