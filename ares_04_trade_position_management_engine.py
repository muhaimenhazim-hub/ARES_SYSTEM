"""
================================================================================
ARES AI TRADING SYSTEM
FILE 04: TRADE & POSITION MANAGEMENT ENGINE
VERSION: 14.1 (SAFE CRYPTO VOLUME FLOOR & DB OPEN_TIME PRESERVATION)
================================================================================
"""

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

        pos = ManagedPosition(
            position_id=pos_id,
            user_id=str(row.get("user_id", "default")),
            mt5_ticket=int(row.get("mt5_ticket", 0)),
            symbol=str(row["symbol"]),
            market=str(row.get("market", "FOREX_OR_INDICES")),
            side=side,
            entry_price=float(row["entry_price"]),
            initial_volume=float(row.get("initial_volume", row["current_volume"])),
            current_volume=float(row["current_volume"]),
            stop_loss=float(row["stop_loss"]),
            initial_stop_loss=float(row.get("initial_stop_loss", row["stop_loss"])),
            tp1=float(row.get("tp1", 0.0)),
            tp2=float(row.get("tp2", 0.0)),
            tp3=float(row.get("tp3", 0.0)),
            risk_amount_usd=float(row.get("risk_amount_usd", 0.0)),
            is_break_even=bool(row.get("is_break_even", 0)),
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
    ) -> Dict[str, Any]:
        if position_id not in self.open_positions:
            return {"status": "NOT_FOUND"}

        pos = self.open_positions[position_id]
        events: List[str] = []

        # محاسبه سود/زیان شناور لحظه‌ای (با در نظر گرفتن اندازه قرارداد فارکس/طلا)
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

        # ۲. بررسی اهداف سود پله‌ای
        if pos.tp1 > 0 and not pos.tp1_hit:
            tp1_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp1) or (
                pos.side == OrderSide.SELL and current_low <= pos.tp1
            )
            if tp1_reached:
                pos.tp1_hit = True
                close_vol = min(pos.current_volume, round(pos.initial_volume * self.tp1_ratio, 6))
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

                fee_buffer = pos.entry_price * (self.taker_fee_pct * 2)
                pos.stop_loss = (pos.entry_price + fee_buffer) if pos.side == OrderSide.BUY else (pos.entry_price - fee_buffer)
                pos.is_break_even = True
                events.append("TP1 محقق شد (۳۰٪ خروج) — حد ضرر به نقطه Break-Even منتقل شد.")

        if pos.tp2 > 0 and pos.tp1_hit and not pos.tp2_hit:
            tp2_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp2) or (
                pos.side == OrderSide.SELL and current_low <= pos.tp2
            )
            if tp2_reached:
                pos.tp2_hit = True
                close_vol = min(pos.current_volume, round(pos.initial_volume * self.tp2_ratio, 6))
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
                pos.stop_loss = pos.tp1
                events.append("TP2 محقق شد (۳۰٪ خروج) — تریلینگ استاپ به سطح TP1 ارتقا یافت.")

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
                events.append("TP3 محقق شد (۴۰٪ پایانی) — معامله با سود کامل بسته شد.")

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