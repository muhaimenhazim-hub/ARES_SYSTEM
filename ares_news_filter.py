"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 3: ECONOMIC NEWS FILTER ENGINE
VERSION: 14.0 (TIMEZONE-AWARE, NON-BLOCKING CACHE & ANTI-RATE-LIMIT)
================================================================================
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import requests


class EconomicNewsFilter:
    """موتور فیلتر اخبار اقتصادی فارکس و کریپتو برای ARES"""

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

        if self.last_fetch_time and (now - self.last_fetch_time).total_seconds() < 1800:
            return self.cached_news

        self.last_fetch_time = now
        try:
            response = requests.get(
                self.CALENDAR_FEED_URL,
                timeout=4,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            if response.status_code == 200:
                all_events = response.json()
                if isinstance(all_events, list):
                    self.cached_news = [
                        event for event in all_events
                        if str(event.get("impact", "")).strip().lower() == "high"
                    ]
            return self.cached_news
        except Exception:
            return self.cached_news

    def is_news_restricted(self, symbol: str) -> Dict:
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
            event_currency = str(event.get("country", "")).strip().upper()
            if event_currency in relevant_currencies:
                event_date_str = event.get("date")
                if not event_date_str:
                    continue

                try:
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