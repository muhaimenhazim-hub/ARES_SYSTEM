---
title: ARES AI Trading System
emoji: 📈
colorFrom: green
colorTo: blue
sdk: docker
app_port: 80
---

# 🏛 ARES AI TRADING SYSTEM (V14.0)

سامانه هوشمند و چندکاربره معاملات الگوریتمی مبتنی بر استراتژی‌های **CRT (Candle Range Theory)** و **SMC / ICT** با قابلیت اتصال مستقیم و دوطرفه به **MetaTrader 5** (از طریق `AresBridgeEA`) و **Binance Futures**.

## ویژگی‌های نسخه ۱۴.۰
- **حذف کامل معاملات شبح (Zero Ghost Trades):** نمایش ۱۰۰٪ واقعی پوزیشن‌های باز و تاریخچه سود/زیان مستقیم از بروکر و صرافی.
- **معماری پایدار ۲۴/۷:** اجرای همزمان موتور تحلیلی (`main.py`) و وب‌دشبورد (`ares_dashboard.py`) روی پورت ۸۰.
- **مدیریت ریسک و سرمایه هوشمند:** محاسبه دقیق حجم بر اساس فاصله حد ضرر (SL)، بررسی جهت قطعی SL/TP و خروج پله‌ای.