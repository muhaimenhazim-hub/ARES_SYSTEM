"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 3: ECONOMIC NEWS FILTER ENGINE
VERSION: 2.0 (TIMEZONE-AWARE & RESILIENT CACHED FEED)
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

    CALENDAR_FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    SYMBOL_CURRENCY_MAP = {
        "BTCUSDT": ["USD"],
        "ETHUSDT": ["USD"],
        "BNBUSDT": ["USD"],
        "ADAUSDT": ["USD"],
        "XRPUSDT": ["USD"],
        "1000PEPEUSDT": ["USD"],
        "XAUUSD": ["USD"],
        "EURUSD": ["EUR", "USD"],
        "NASDAQ 100": ["USD"],
        "S&P 500": ["USD"],
    }

    def __init__(self, blackout_window_minutes: int = 30):
        self.blackout_minutes = blackout_window_minutes
        self.cached_news: List[Dict] = []
        self.last_fetch_time: Optional[datetime] = None

    def fetch_high_impact_news(self) -> List[Dict]:
        now = datetime.now(timezone.utc)

        if self.cached_news and self.last_fetch_time:
            if (now - self.last_fetch_time).total_seconds() < 1800:
                return self.cached_news

        try:
            response = requests.get(self.CALENDAR_FEED_URL, timeout=5)
            if response.status_code == 200:
                all_events = response.json()
                high_impact = [
                    event for event in all_events
                    if str(event.get("impact", "")).strip().lower() == "high"
                ]
                self.cached_news = high_impact
                self.last_fetch_time = now
                return high_impact
            else:
                return self.cached_news
        except Exception:
            return self.cached_news

    def is_news_restricted(self, symbol: str) -> Dict:
        high_news = self.fetch_high_impact_news()
        if not high_news:
            return {
                "restricted": False,
                "reason": "هیچ خبر مهمی در حال حاضر وجود ندارد یا تقویم در دسترس نیست.",
                "event": None,
            }

        now = datetime.now(timezone.utc)
        relevant_currencies = self.SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])

        for event in high_news:
            event_currency = str(event.get("country", "")).strip().upper()
            if event_currency in relevant_currencies:
                event_date_str = event.get("date")
                if not event_date_str:
                    continue

                try:
                    # تضمین تبدیل به زمان دارای آگاهی تایم‌زون UTC
                    event_time = datetime.fromisoformat(event_date_str.replace("Z", "+00:00"))
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                    else:
                        event_time = event_time.astimezone(timezone.utc)

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