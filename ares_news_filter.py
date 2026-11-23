"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 3: ECONOMIC NEWS FILTER ENGINE
VERSION: 14.1 (30M BLACKOUT + MT5 LIVE CALENDAR ACTUAL/FORECAST/PREV ANALYSIS)
================================================================================
"""

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIVE_CALENDAR_FILE = os.path.join(BASE_DIR, "ares_live_calendar.json")
LIVE_CALENDAR_MAX_AGE_SECONDS = 300.0


class EconomicNewsFilter:
    """موتور فیلتر اخبار اقتصادی فارکس و کریپتو همراه با تحلیل تقویم زنده متاتریدر"""

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

    INVERSE_INDICATOR_KEYWORDS = (
        "unemployment",
        "jobless",
        "claims",
    )

    def __init__(self, blackout_window_minutes: int = 30):
        self.blackout_minutes = blackout_window_minutes
        self.cached_news: List[Dict] = []
        self.last_fetch_time: Optional[datetime] = None
        self._live_cal_cache: List[Dict[str, Any]] = []
        self._live_cal_mtime: float = 0.0
        self._live_cal_updated_ts: float = 0.0

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

    def _load_mt5_live_calendar(self) -> List[Dict[str, Any]]:
        if not os.path.exists(LIVE_CALENDAR_FILE):
            return []
        try:
            mtime = os.path.getmtime(LIVE_CALENDAR_FILE)
            now_ts = time.time()
            if mtime == self._live_cal_mtime and self._live_cal_cache:
                if (now_ts - self._live_cal_updated_ts) <= LIVE_CALENDAR_MAX_AGE_SECONDS:
                    return self._live_cal_cache
                return []

            with open(LIVE_CALENDAR_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return []
            updated_ts = float(payload.get("updated_ts", 0.0) or 0.0)
            events = payload.get("events", [])
            if not isinstance(events, list):
                return []

            self._live_cal_mtime = mtime
            self._live_cal_updated_ts = updated_ts
            self._live_cal_cache = [ev for ev in events if isinstance(ev, dict)]

            if updated_ts <= 0.0 or (now_ts - updated_ts) > LIVE_CALENDAR_MAX_AGE_SECONDS:
                return []
            return self._live_cal_cache
        except Exception:
            return []

    @staticmethod
    def _safe_float(val: Any) -> Optional[float]:
        if val is None or isinstance(val, bool):
            return None
        try:
            num = float(val)
            return num if math.isfinite(num) else None
        except (TypeError, ValueError):
            return None

    def _is_inverse_indicator(self, title: str) -> bool:
        t_low = str(title or "").lower()
        return any(kw in t_low for kw in self.INVERSE_INDICATOR_KEYWORDS)

    def analyze_post_news_impact(
        self,
        symbol: str,
        lookback_minutes: int = 180,
    ) -> Dict[str, Any]:
        """تحلیل تقویم زنده متاتریدر بعد از انتشار خبر (Actual در برابر Forecast و Previous)"""
        events = self._load_mt5_live_calendar()
        if not events:
            return {
                "has_data": False,
                "news_bias": "NEUTRAL",
                "confidence": 0.0,
                "summary": "داده جدیدی در تقویم زنده متاتریدر موجود نیست.",
                "events": [],
            }

        now_ts = time.time()
        max_age_sec = float(lookback_minutes) * 60.0
        relevant_currencies = self.SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])

        symbol_score = 0.0
        total_weight = 0.0
        analyzed_events: List[Dict[str, Any]] = []

        for ev in events:
            currency = str(ev.get("currency", "")).strip().upper()
            if currency not in relevant_currencies:
                continue

            impact = str(ev.get("impact", "")).strip().upper()
            if impact not in ("HIGH", "MODERATE"):
                continue

            ev_ts = self._safe_float(ev.get("time_ts"))
            if ev_ts is None or ev_ts <= 0:
                continue
            elapsed = now_ts - ev_ts
            if elapsed < 0 or elapsed > max_age_sec:
                continue

            if not bool(ev.get("has_actual")):
                continue

            actual = self._safe_float(ev.get("actual"))
            forecast = self._safe_float(ev.get("forecast")) if bool(ev.get("has_forecast")) else None
            previous = self._safe_float(ev.get("previous")) if bool(ev.get("has_previous")) else None
            if actual is None:
                continue

            ref_val = forecast if forecast is not None else previous
            if ref_val is None:
                continue

            title = str(ev.get("title", "")).strip()
            diff = actual - ref_val
            if abs(diff) <= 1e-12:
                curr_effect = "NEUTRAL"
                curr_dir = 0.0
            else:
                raw_sign = 1.0 if diff > 0 else -1.0
                if self._is_inverse_indicator(title):
                    raw_sign = -raw_sign
                curr_dir = raw_sign
                curr_effect = "BULLISH" if curr_dir > 0 else "BEARISH"

                # تقویت وزن در صورت هم‌جهت بودن هم‌زمان با Forecast و Previous
                if forecast is not None and previous is not None:
                    prev_diff = actual - previous
                    prev_sign = 1.0 if prev_diff > 0 else (-1.0 if prev_diff < 0 else 0.0)
                    if self._is_inverse_indicator(title):
                        prev_sign = -prev_sign
                    if prev_sign == curr_dir:
                        curr_dir *= 1.25

            weight = 2.0 if impact == "HIGH" else 1.0
            # نگاشت اثر ارز به جهت نماد معاملاتی
            if symbol == "EURUSD":
                sym_sign = 1.0 if currency == "EUR" else -1.0
            else:
                sym_sign = -1.0 if currency == "USD" else 1.0

            symbol_score += curr_dir * sym_sign * weight
            total_weight += weight

            analyzed_events.append({
                "title": title,
                "currency": currency,
                "impact": impact,
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "currency_effect": curr_effect,
                "minutes_since_release": round(elapsed / 60.0, 1),
            })

        if not analyzed_events or total_weight <= 0.0:
            return {
                "has_data": False,
                "news_bias": "NEUTRAL",
                "confidence": 0.0,
                "summary": "در ۳ ساعت اخیر خبر منتشرشده‌ای با عدد Actual برای این نماد ثبت نشده است.",
                "events": [],
            }

        norm_score = symbol_score / total_weight
        confidence = min(1.0, abs(norm_score))
        if norm_score >= 0.25:
            news_bias = "BUY"
        elif norm_score <= -0.25:
            news_bias = "SELL"
        else:
            news_bias = "NEUTRAL"

        latest = analyzed_events[-1]
        summary = (
            f"تحلیل تقویم زنده ({latest['currency']} | {latest['title']}): "
            f"Actual={latest['actual']} در برابر Forecast={latest['forecast']} / Prev={latest['previous']} "
            f"-> فشار خبری نماد: {news_bias}"
        )

        return {
            "has_data": True,
            "news_bias": news_bias,
            "confidence": round(confidence, 2),
            "summary": summary,
            "events": analyzed_events,
        }

    def is_news_restricted(self, symbol: str) -> Dict:
        now = datetime.now(timezone.utc)
        now_ts = now.timestamp()
        relevant_currencies = self.SYMBOL_CURRENCY_MAP.get(symbol, ["USD"])
        post_news = self.analyze_post_news_impact(symbol)

        # ۱. بررسی فید رسمی هفتگی ForexFactory (۳۰ دقیقه قبل و بعد از خبر مهم)
        high_news = self.fetch_high_impact_news()
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
                            "post_news_analysis": post_news,
                        }
                except Exception:
                    continue

        # ۲. بررسی تقویم زنده متاتریدر (پوشش پشتیبان برای ۳۰ دقیقه قبل و بعد از خبر مهم)
        blackout_sec = float(self.blackout_minutes) * 60.0
        for ev in self._load_mt5_live_calendar():
            ev_curr = str(ev.get("currency", "")).strip().upper()
            ev_imp = str(ev.get("impact", "")).strip().upper()
            if ev_curr in relevant_currencies and ev_imp == "HIGH":
                ev_ts = self._safe_float(ev.get("time_ts"))
                if ev_ts is not None and abs(ev_ts - now_ts) <= blackout_sec:
                    diff_minutes = (ev_ts - now_ts) / 60.0
                    return {
                        "restricted": True,
                        "reason": f"خبر مهم تقویم زنده MT5 ({ev.get('title')}) برای ارز {ev_curr} در بازه ۳۰ دقیقه‌ای است.",
                        "event": ev.get("title"),
                        "currency": ev_curr,
                        "minutes_to_event": round(diff_minutes, 1),
                        "post_news_analysis": post_news,
                    }

        return {
            "restricted": False,
            "reason": "هیچ خبر دارای ریسک مهم در بازه زمانی جاری وجود ندارد.",
            "event": None,
            "post_news_analysis": post_news,
        }