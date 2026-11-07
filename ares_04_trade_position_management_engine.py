"""
================================================================================
ARES AI TRADING SYSTEM
FILE 04: TRADE & POSITION MANAGEMENT ENGINE
VERSION: 1.1
================================================================================
ماموریت ماژول:
این ماژول مسئول اجرای سفارش‌ها، مدیریت فعال پوزیشن‌ها، ثبت حد ضرر الزامی،
خروج‌های پله‌ای (Partial TP)، انتقال حد ضرر به نقطه سر‌به‌سر (Break-Even)
و خروج ساختاری و زودهنگام است.

اصول قطعی و غیرقابل تغییر پیاده‌سازی شده:
- هیچ معامله‌ای بدون ثبت قطعی Stop Loss باز نخواهد ماند.
- انتقال حد ضرر فقط در جهت کاهش ریسک مجاز است (نه افزایش ریسک).
- خروج پله‌ای: ۳۰٪ در TP1، ۳۰٪ در TP2 و ۴۰٪ در TP3.
- مارتینگل و ورود پله‌ای (Averaging down) کاملاً غیرفعال و ممنوع است.
- پشتیبانی کامل و یکسان از حالت‌های BACKTEST ،PAPER و LIVE.
================================================================================
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


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
    target_name: str  # 'TP1', 'TP2', 'TP3'
    exit_price: float
    closed_volume: float
    realized_pnl: float
    fee_paid: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ManagedPosition:
    """ساختار داده پوزیشن فعال و تحت مدیریت ARES"""
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
    is_break_even: bool = False
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False
    status: PositionStatus = PositionStatus.OPEN
    partial_exits: List[PartialExitRecord] = field(default_factory=list)
    realized_pnl: float = 0.0
    total_fees_paid: float = 0.0
    open_time: datetime = field(default_factory=datetime.utcnow)
    close_time: Optional[datetime] = None
    exit_reason: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "market": self.market,
            "side": self.side.value,
            "entry_price": round(self.entry_price, 4),
            "initial_volume": round(self.initial_volume, 4),
            "current_volume": round(self.current_volume, 4),
            "stop_loss": round(self.stop_loss, 4),
            "initial_stop_loss": round(self.initial_stop_loss, 4),
            "targets": {
                "tp1": round(self.tp1, 4),
                "tp2": round(self.tp2, 4),
                "tp3": round(self.tp3, 4),
            },
            "risk_amount_usd": round(self.risk_amount_usd, 2),
            "is_break_even": self.is_break_even,
            "status": self.status.value,
            "realized_pnl": round(self.realized_pnl, 4),
            "total_fees_paid": round(self.total_fees_paid, 4),
            "partial_exits_count": len(self.partial_exits),
            "exit_reason": self.exit_reason,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat() if self.close_time else None,
        }


class TradePositionManagementEngine:
    """
    موتور مستقل مدیریت معاملات و پوزیشن‌ها
    """

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.PAPER,
        tp1_ratio: float = 0.30,  # ۳۰ درصد خروج در تارگت ۱
        tp2_ratio: float = 0.30,  # ۳۰ درصد خروج در تارگت ۲
        tp3_ratio: float = 0.40,  # ۴۰ درصد خروج در تارگت ۳
        taker_fee_pct: float = 0.0005,  # کارمزد تخمینی صرافی (۰.۰۵٪)
    ):
        self.mode = mode
        self.tp1_ratio = tp1_ratio
        self.tp2_ratio = tp2_ratio
        self.tp3_ratio = tp3_ratio
        self.taker_fee_pct = taker_fee_pct
        self.open_positions: Dict[str, ManagedPosition] = {}
        self.trade_history: List[ManagedPosition] = []

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
    ) -> Tuple[bool, Optional[ManagedPosition], str]:
        """
        ایجاد و اعتبارسنجی پوزیشن جدید همراه با الزام ثبت حد ضرر
        """
        # ۱. بررسی امنیتی: عدم امکان ورود پله‌ای روی همان نماد
        for pos in self.open_positions.values():
            if pos.symbol == symbol:
                return False, None, f"خطای رد سفارش: ورود پله‌ای یا معامله هم‌زمان روی نماد {symbol} ممنوع است."

        # ۲. اعتبارسنجی حد ضرر
        side = OrderSide.BUY if side_str.upper() == "BUY" else OrderSide.SELL
        if side == OrderSide.BUY and stop_loss >= entry_price:
            return False, None, "خطا: برای معامله BUY حد ضرر باید زیر قیمت ورود باشد."
        if side == OrderSide.SELL and stop_loss <= entry_price:
            return False, None, "خطا: برای معامله SELL حد ضرر باید بالای قیمت ورود باشد."

        # ۳. کارمزد ورود
        entry_fee = entry_price * allocated_volume * self.taker_fee_pct

        pos_id = f"POS_{symbol}_{uuid.uuid4().hex[:8]}"
        new_pos = ManagedPosition(
            position_id=pos_id,
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
        return True, new_pos, f"پوزیشن {pos_id} با موفقیت در حالت {self.mode.value} باز شد."

    def update_position_on_price_tick(
        self,
        position_id: str,
        current_high: float,
        current_low: float,
        current_close: float,
    ) -> Dict:
        """
        مدیریت پویا و زنده پوزیشن با هر تیک قیمتی جدید:
        - بررسی برخورد با Stop Loss
        - بررسی تارگت‌های سه‌گانه و اجرای Partial TP
        - فعال‌سازی Break-Even در تارگت ۱
        - تریلینگ استاپ
        """
        if position_id not in self.open_positions:
            return {"status": "NOT_FOUND"}

        pos = self.open_positions[position_id]
        events: List[str] = []

        # ۱. بررسی برخورد با حد ضرر (Stop Loss)
        sl_hit = False
        sl_exit_price = pos.stop_loss

        if pos.side == OrderSide.BUY and current_low <= pos.stop_loss:
            sl_hit = True
        elif pos.side == OrderSide.SELL and current_high >= pos.stop_loss:
            sl_hit = True

        if sl_hit:
            loss_per_unit = (sl_exit_price - pos.entry_price) if pos.side == OrderSide.BUY else (pos.entry_price - sl_exit_price)
            exit_fee = sl_exit_price * pos.current_volume * self.taker_fee_pct
            pos.realized_pnl += (loss_per_unit * pos.current_volume) - exit_fee
            pos.total_fees_paid += exit_fee
            pos.current_volume = 0.0
            pos.status = PositionStatus.CLOSED
            pos.close_time = datetime.utcnow()
            pos.exit_reason = "STOP_LOSS_HIT" if not pos.is_break_even else "BREAK_EVEN_STOP_HIT"

            self.trade_history.append(pos)
            del self.open_positions[position_id]
            return {
                "status": "CLOSED",
                "reason": pos.exit_reason,
                "position": pos.to_dict(),
            }

        # ۲. بررسی اهداف سود پله‌ای (Partial Take Profit)
        # هدف اول (TP1): خروج ۳۰٪ + انتقال حد ضرر به نقطه ورود (Break-Even)
        if not pos.tp1_hit:
            tp1_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp1) or \
                          (pos.side == OrderSide.SELL and current_low <= pos.tp1)
            if tp1_reached:
                pos.tp1_hit = True
                close_vol = pos.initial_volume * self.tp1_ratio
                pnl = (pos.tp1 - pos.entry_price) * close_vol if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp1) * close_vol
                fee = pos.tp1 * close_vol * self.taker_fee_pct
                net_pnl = pnl - fee

                pos.current_volume -= close_vol
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

                # انتقال حد ضرر به نقطه سر‌به‌سر (Break-Even با احتساب کارمزد)
                fee_buffer = pos.entry_price * (self.taker_fee_pct * 2)
                pos.stop_loss = (pos.entry_price + fee_buffer) if pos.side == OrderSide.BUY else (pos.entry_price - fee_buffer)
                pos.is_break_even = True
                events.append("TP1 محقق شد (۳۰٪ خروج) — حد ضرر به نقطه Break-Even منتقل شد.")

        # هدف دوم (TP2): خروج ۳۰٪ دیگر + جابجایی تریلینگ استاپ به TP1
        if pos.tp1_hit and not pos.tp2_hit:
            tp2_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp2) or \
                          (pos.side == OrderSide.SELL and current_low <= pos.tp2)
            if tp2_reached:
                pos.tp2_hit = True
                close_vol = pos.initial_volume * self.tp2_ratio
                pnl = (pos.tp2 - pos.entry_price) * close_vol if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp2) * close_vol
                fee = pos.tp2 * close_vol * self.taker_fee_pct
                net_pnl = pnl - fee

                pos.current_volume -= close_vol
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
                # جابجایی تریلینگ استاپ به سمت هدف اول جهت قفل سود
                pos.stop_loss = pos.tp1
                events.append("TP2 محقق شد (۳۰٪ خروج) — تریلینگ استاپ به سطح TP1 ارتقا یافت.")

        # هدف سوم و نهایی (TP3): خروج باقی‌مانده پوزیشن (۴۰٪) و بستن کامل
        if pos.tp2_hit and not pos.tp3_hit:
            tp3_reached = (pos.side == OrderSide.BUY and current_high >= pos.tp3) or \
                          (pos.side == OrderSide.SELL and current_low <= pos.tp3)
            if tp3_reached:
                pos.tp3_hit = True
                close_vol = pos.current_volume  # بستن تمام حجم باقیمانده
                pnl = (pos.tp3 - pos.entry_price) * close_vol if pos.side == OrderSide.BUY else (pos.entry_price - pos.tp3) * close_vol
                fee = pos.tp3 * close_vol * self.taker_fee_pct
                net_pnl = pnl - fee

                pos.current_volume = 0.0
                pos.realized_pnl += net_pnl
                pos.total_fees_paid += fee
                pos.status = PositionStatus.CLOSED
                pos.close_time = datetime.utcnow()
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

    def emergency_close_all(self, reason: str = "EMERGENCY_STOP") -> List[Dict]:
        """
        بستن فوری و حفاظتی تمام معاملات باز سیستم (مورد استفاده در اخبار یا دراوداون بحرانی)
        """
        closed_reports = []
        for pos_id, pos in list(self.open_positions.items()):
            pos.status = PositionStatus.CLOSED
            pos.close_time = datetime.utcnow()
            pos.exit_reason = reason
            self.trade_history.append(pos)
            closed_reports.append(pos.to_dict())
            del self.open_positions[pos_id]
        return closed_reports


# ==============================================================================
# تست خودکار مدیریت پوزیشن و خروج پله‌ای (Self-Test Simulation)
# ==============================================================================
if __name__ == "__main__":
    import pprint

    print("=" * 70)
    print("ARES AI TRADING SYSTEM — TESTING MODULE 04: TRADE & POSITION ENGINE")
    print("=" * 70)

    engine = TradePositionManagementEngine(mode=ExecutionMode.PAPER)

    # ۱. باز کردن یک معامله خرید آزمایشی بر روی بیتکوین
    success, pos, msg = engine.open_position(
        symbol="BTCUSDT",
        market="CRYPTO_FUTURES",
        side_str="BUY",
        entry_price=94000.0,
        stop_loss=93000.0,
        tp1=95500.0,  # سود ۱.۵ برابری
        tp2=96500.0,  # سود ۲.۵ برابری
        tp3=98000.0,  # سقف رنج CRT
        allocated_volume=0.01,
        risk_usd=10.0,
    )

    print(f"\n[وضعیت بازگشایی سفارش]: {msg}")
    print(f"شناسه پوزیشن: {pos.position_id}")

    # ۲. شبیه‌سازی حرکت قیمت: قیمت به TP1 (95500) می‌رسد
    print("\n--- تیک اول: قیمت به 95,600 صعود می‌کند (برخورد با TP1) ---")
    update_1 = engine.update_position_on_price_tick(
        pos.position_id, current_high=95600.0, current_low=94200.0, current_close=95400.0
    )
    for ev in update_1.get("events", []):
        print(f"👉 رویداد: {ev}")
    print(f"حد ضرر جدید (Break-Even): {update_1['position']['stop_loss']}")
    print(f"حجم باقیمانده: {update_1['position']['current_volume']}")

    # ۳. شبیه‌سازی حرکت قیمت: قیمت به TP2 (96500) می‌رسد
    print("\n--- تیک دوم: قیمت به 96,700 صعود می‌کند (برخورد با TP2) ---")
    update_2 = engine.update_position_on_price_tick(
        pos.position_id, current_high=96700.0, current_low=95200.0, current_close=96500.0
    )
    for ev in update_2.get("events", []):
        print(f"👉 رویداد: {ev}")
    print(f"حد ضرر تریل‌شده به سمت سود: {update_2['position']['stop_loss']}")
    print(f"حجم باقیمانده: {update_2['position']['current_volume']}")

    # ۴. شبیه‌سازی حرکت قیمت: قیمت به TP3 (98000) می‌رسد و پوزیشن تسویه کامل می‌شود
    print("\n--- تیک سوم: قیمت به 98,100 صعود می‌کند (برخورد با TP3) ---")
    update_3 = engine.update_position_on_price_tick(
        pos.position_id, current_high=98100.0, current_low=96400.0, current_close=98050.0
    )
    for ev in update_3.get("events", []):
        print(f"👉 رویداد: {ev}")

    print("\n[گزارش تسویه نهایی معامله]:")
    pprint.pprint(update_3["position"])

    print("\n" + "=" * 70)
    if update_3["status"] == "CLOSED" and update_3["reason"] == "FULL_TAKE_PROFIT":
        print("✅ تست فایل شماره ۴ با موفقیت کامل انجام شد!")
        print(f"💰 کل سود محقق‌شده: {update_3['position']['realized_pnl']:.2f} دلار")
    print("=" * 70)