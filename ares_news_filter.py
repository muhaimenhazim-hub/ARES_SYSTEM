"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 3: ECONOMIC NEWS FILTER ENGINE
VERSION: 1.1
================================================================================
ماموریت ماژول:
بررسی تقویم رویدادهای اقتصادی معتبر و فیلتر کردن معاملات در زمان انتشار اخبار مهم:
- اعمال قانون ممنوعیت ورود از ۳۰ دقیقه قبل تا ۳۰ دقیقه بعد از اخبار High Impact
- نقشه‌برداری ارزهای خبر به نمادهای بازار (USD, EUR)
- حفاظت از سرمایه در برابر نوسانات شدید و لغزش قیمت (Slippage) ناشی از اخبار
================================================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import requests


class EconomicNewsFilter:
    """
    موتور فیلتر اخبار اقتصادی فارکس و کریپتو برای ARES
    """

    # آدرس فید استاندارد و رسمی تقویم اقتصادی هفتگی
    CALENDAR_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    # نگاشت ارزهای تحت تاثیر برای هر نماد معاملاتی
    SYMBOL_CURRENCY_MAP = {
        # کریپتو تحت تاثیر اخبار کلان دلار آمریکا
        "BTCUSDT": ["USD"],
        "ETHUSDT": ["USD"],
        "BNBUSDT": ["USD"],
        "ADAUSDT": ["USD"],
        "XRPUSDT": ["USD"],
        "1000PEPEUSDT": ["USD"],
        # فارکس
        "XAUUSD": ["USD"],
        "EURUSD": ["EUR", "USD"],
        # شاخص‌ها
        "NASDAQ 100": ["USD"],
        "S&P 500": ["USD"],
    }

    def __init__(self, blackout_window_minutes: int = 30):
        """
        :param blackout_window_minutes: مدت زمان ممنوعیت ورود قبل و بعد از خبر (۳۰ دقیقه طبق سند)
        """
        self.blackout_minutes = blackout_window_minutes
        self.cached_news: List[Dict] = []
        self.last_fetch_time: Optional[datetime] = None

    def fetch_high_impact_news(self) -> List[Dict]:
        """
        دریافت آنلاین و بدون فیلتر اخبار با درجه تاثیر بالا (High Impact)
        """
        now = datetime.now(timezone.utc)

        # اگر کمتر از ۳۰ دقیقه از آخرین دریافت گذشته باشد، از حافظه کش استفاده کن
        if self.cached_news and self.last_fetch_time:
            if (now - self.last_fetch_time).total_seconds() < 1800:
                return self.cached_news

        try:
            response = requests.get(self.CALENDAR_FEED_URL, timeout=10)
            if response.status_code == 200:
                all_events = response.json()
                # فقط اخباری که اهمیت بالا (High) دارند فیلتر می‌شوند
                high_impact = [
                    event for event in all_events
                    if event.get("impact") == "High"
                ]
                self.cached_news = high_impact
                self.last_fetch_time = now
                print(f"📰 تقویم اقتصادی به‌روزرسانی شد: {len(high_impact)} رویداد High Impact این هفته ثبت گردید.")
                return high_impact
            else:
                print(f"⚠️ سرور تقویم اخبار پاسخ نداد (کد وضعیت: {response.status_code}).")
                return self.cached_news
        except Exception as e:
            print(f"⚠️ خطای موقت در اتصال به سرور اخبار: {e}")
            return self.cached_news

    def is_news_restricted(self, symbol: str) -> Dict:
        """
        بررسی اینکه آیا نماد انتخابی در بازه ۳۰ دقیقه قبل تا ۳۰ دقیقه بعد از خبر مهم است یا خیر
        """
        high_news = self.fetch_high_impact_news()
        if not high_news:
            return {
                "restricted": False,
                "reason": "هیچ خبر مهمی در حال حاضر وجود ندارد.",
                "event": None,
            }

        now = datetime.now(timezone.utc)
        relevant_currencies = self.SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])

        for event in high_news:
            event_currency = event.get("country")
            if event_currency in relevant_currencies:
                event_date_str = event.get("date")  # فرمت: 2025-01-01T13:30:00-05:00
                if not event_date_str:
                    continue

                try:
                    event_time = datetime.fromisoformat(event_date_str)
                    start_blackout = event_time - timedelta(minutes=self.blackout_minutes)
                    end_blackout = event_time + timedelta(minutes=self.blackout_minutes)

                    if start_blackout <= now <= end_blackout:
                        diff_minutes = (event_time - now).total_seconds() / 60.0
                        return {
                            "restricted": True,
                            "reason": f"خبر با اهمیت بالا ({event.get('title')}) برای ارز {event_currency} در محدوده ۳۰ دقیقه‌ای قرار دارد.",
                            "event": event.get("title"),
                            "currency": event_currency,
                            "minutes_to_event": round(diff_minutes, 1),
                        }
                except Exception:
                    continue

        return {
            "restricted": False,
            "reason": "هیچ خبر دارای ریسک مهم در بازه زمانی جاری وجود ندارد.",
            "event": None,
        }


# ==============================================================================
# تست زنده فیلتر اخبار اقتصادی
# ==============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("ARES AI TRADING SYSTEM — TESTING ECONOMIC NEWS FILTER ENGINE")
    print("=" * 70)

    news_filter = EconomicNewsFilter(blackout_window_minutes=30)
    events = news_filter.fetch_high_impact_news()

    print(f"\nتعداد اخبار High Impact کشف شده برای این هفته: {len(events)}")
    if events:
        print("\nنمونه‌ای از مهم‌ترین اخبار این هفته:")
        for ev in events[:4]:
            print(f"👉 [{ev.get('country')}] {ev.get('title')} — تاریخ و زمان: {ev.get('date')}")

    # آزمایش بررسی ممنوعیت روی نماد طلا و بیت‌کوین
    print("\n--- بررسی وضعیت نماد XAUUSD (طلا) ---")
    status_gold = news_filter.is_news_restricted("XAUUSD")
    print(f"آیا معامله ممنوع است؟ {status_gold['restricted']}")
    print(f"توضیحات: {status_gold['reason']}")

    print("\n--- بررسی وضعیت نماد BTCUSDT (بیت‌کوین) ---")
    status_btc = news_filter.is_news_restricted("BTCUSDT")
    print(f"آیا معامله ممنوع است؟ {status_btc['restricted']}")
    print(f"توضیحات: {status_btc['reason']}")

    print("\n" + "=" * 70)
    print("✅ موتور فیلتر اخبار با موفقیت کامل آماده و فعال گردید.")
    print("=" * 70)