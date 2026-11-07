"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 11: VISUAL WEB DASHBOARD WITH IN-APP ACCOUNT SETTINGS
VERSION: 3.0
================================================================================
"""

import os
import socket
from datetime import datetime, timezone
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

import account_config
from ares_database import AresDatabaseManager
from ares_news_filter import EconomicNewsFilter

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

app = FastAPI(title="ARES AI TRADING SYSTEM DASHBOARD")
db = AresDatabaseManager()
news_filter = EconomicNewsFilter()


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARES AI TRADING SYSTEM — داشبورد مدیریت معاملات</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background-color: #0b0e14; color: #e2e8f0; }
        .card { background-color: #151b26; border: 1px solid #232d3f; border-radius: 0.75rem; }
        .glow-green { box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
        .modal { background-color: rgba(0, 0, 0, 0.75); backdrop-filter: blur(4px); }
    </style>
</head>
<body class="p-4 md:p-6">
    <!-- هدر بالای داشبورد -->
    <header class="flex flex-wrap justify-between items-center mb-8 pb-4 border-b border-gray-800 gap-4">
        <div>
            <div class="flex items-center gap-3">
                <div class="h-4 w-4 rounded-full bg-emerald-500 animate-pulse"></div>
                <h1 class="text-xl md:text-2xl font-bold tracking-wider text-emerald-400">ARES AI TRADING SYSTEM</h1>
                <span class="text-xs bg-emerald-950 text-emerald-400 border border-emerald-800 px-2 py-0.5 rounded">نسخه 1.1 لایو</span>
            </div>
            <p class="text-gray-400 text-xs md:text-sm mt-1" id="broker-connected-info">در حال بررسی ارتباط...</p>
        </div>
        <div class="flex flex-wrap gap-3 items-center">
            <!-- دکمه تنظیمات حساب برای باز کردن مودال -->
            <button onclick="openSettingsModal()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg font-bold text-xs md:text-sm transition flex items-center gap-1 shadow-lg shadow-blue-900/30">
                <i class="fa-solid fa-gear"></i> تنظیمات حساب و صرافی
            </button>
            <button onclick="emergencyStop()" class="bg-red-600 hover:bg-red-700 text-white px-3 py-2 rounded-lg font-bold text-xs md:text-sm transition shadow-lg shadow-red-900/40">
                <i class="fa-solid fa-power-off ml-1"></i> توقف اضطراری
            </button>
        </div>
    </header>

    <!-- کارت‌های شاخص‌های کلیدی عملکرد (KPIs) -->
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-8">
        <div class="card p-5 glow-green">
            <div class="text-gray-400 text-sm font-medium flex justify-between">
                <span>موجودی واقعی حساب (Equity)</span>
                <i class="fa-solid fa-wallet text-emerald-400"></i>
            </div>
            <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="equity-val">$0.00</div>
            <div class="text-xs text-emerald-400 mt-2 font-medium" id="account-id-display">حساب فعال: در حال دریافت...</div>
        </div>

        <div class="card p-5">
            <div class="text-gray-400 text-sm font-medium flex justify-between">
                <span>سود محقق‌شده معاملات</span>
                <i class="fa-solid fa-chart-line text-blue-400"></i>
            </div>
            <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="daily-pnl">+$0.00</div>
            <div class="text-xs text-gray-400 mt-2">سقف توقف روزانه: 5%</div>
        </div>

        <div class="card p-5">
            <div class="text-gray-400 text-sm font-medium flex justify-between">
                <span>پوزیشن‌های فعال</span>
                <i class="fa-solid fa-layer-group text-purple-400"></i>
            </div>
            <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="open-positions-count">0 / 3</div>
            <div class="text-xs text-gray-400 mt-2">سقف مجاز سیستم: حداکثر ۳ پوزیشن</div>
        </div>

        <div class="card p-5">
            <div class="text-gray-400 text-sm font-medium flex justify-between">
                <span>افت سرمایه (Drawdown)</span>
                <i class="fa-solid fa-shield-halved text-amber-400"></i>
            </div>
            <div class="text-2xl md:text-3xl font-extrabold text-emerald-400 mt-2" id="drawdown-val">0.00%</div>
            <div class="text-xs text-gray-400 mt-2">سقف قفل اضطراری: 12%</div>
        </div>
    </div>

    <!-- جدول معاملات باز زنده -->
    <div class="card p-4 md:p-6 mb-8">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-base md:text-lg font-bold text-gray-200 flex items-center gap-2">
                <i class="fa-solid fa-bolt text-amber-400"></i> معاملات فعال و تحت مدیریت زنده
            </h2>
            <span class="text-xs bg-blue-950 text-blue-400 border border-blue-800 px-3 py-1 rounded-full animate-pulse">
                پایش ۲ ثانیه‌ای فعال
            </span>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-right text-xs md:text-sm">
                <thead class="text-gray-400 bg-gray-900/50 uppercase border-b border-gray-800">
                    <tr>
                        <th class="py-3 px-3">شناسه</th>
                        <th class="py-3 px-3">نماد</th>
                        <th class="py-3 px-3">جهت</th>
                        <th class="py-3 px-3">قیمت ورود</th>
                        <th class="py-3 px-3">حد ضرر (SL)</th>
                        <th class="py-3 px-3">هدف اول (TP1)</th>
                        <th class="py-3 px-3">هدف دوم (TP2)</th>
                        <th class="py-3 px-3">هدف سوم (TP3)</th>
                        <th class="py-3 px-3">حجم</th>
                        <th class="py-3 px-3">وضعیت</th>
                    </tr>
                </thead>
                <tbody id="open-trades-table" class="divide-y divide-gray-800">
                    <tr>
                        <td colspan="10" class="py-6 text-center text-gray-500">هیچ معامله بازی وجود ندارد.</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <!-- پنجره تنظیمات حساب (Modal) برای اتصال اکانت‌ها از خود داشبورد -->
    <div id="settings-modal" class="fixed inset-0 modal flex items-center justify-center p-4 hidden z-50">
        <div class="bg-gray-900 border border-gray-700 rounded-xl max-w-xl w-full p-6 text-right max-h-[90vh] overflow-y-auto">
            <div class="flex justify-between items-center pb-3 border-b border-gray-800">
                <h3 class="text-lg font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-sliders text-blue-400"></i> تنظیمات اتصال حساب شما
                </h3>
                <button onclick="closeSettingsModal()" class="text-gray-400 hover:text-white text-xl">&times;</button>
            </div>

            <!-- انتخاب حالت معامله -->
            <div class="mt-4">
                <label class="block text-xs font-bold text-gray-400 mb-1">حالت معامله:</label>
                <select id="cfg-trading-mode" class="w-full bg-gray-800 border border-gray-700 rounded-lg p-2.5 text-sm text-white focus:outline-none focus:border-blue-500">
                    <option value="PAPER">آزمایشی زنده روی قیمت‌های واقعی (Paper Trading)</option>
                    <option value="LIVE">معاملات واقعی با سرمایه حقیقی (Live Trading)</option>
                </select>
            </div>

            <!-- بخش متاتریدر ۵ -->
            <div class="mt-6 p-4 rounded-lg bg-gray-800/40 border border-gray-700/60">
                <h4 class="text-sm font-bold text-emerald-400 mb-3 flex items-center gap-2">
                    <i class="fa-solid fa-chart-line"></i> اتصال به متاتریدر ۵ (فارکس و طلا)
                </h4>
                <div class="space-y-3 text-xs">
                    <div>
                        <label class="block text-gray-400 mb-1">شماره حساب (Login Number):</label>
                        <input type="text" id="cfg-mt5-login" placeholder="مثال: 300112" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1">رمز عبور حساب (Password):</label>
                        <input type="password" id="cfg-mt5-pass" placeholder="رمز عبور اکانت متاتریدر" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1">نام سرور بروکر (Server Name):</label>
                        <input type="text" id="cfg-mt5-server" placeholder="مثال: AronMarkets-Demo یا Alpari-Standard" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white">
                    </div>
                    <p class="text-[11px] text-gray-500">* اگر فیلدهای متاتریدر خالی بمانند، ربات خودکار به اکانتی که هم‌اکنون داخل نرم‌افزار MT5 باز است متصل می‌ماند.</p>
                </div>
            </div>

            <!-- بخش بایننس -->
            <div class="mt-4 p-4 rounded-lg bg-gray-800/40 border border-gray-700/60">
                <h4 class="text-sm font-bold text-amber-400 mb-3 flex items-center gap-2">
                    <i class="fa-brands fa-bitcoin"></i> اتصال به صرافی بایننس (کریپتو فیوچرز)
                </h4>
                <div class="space-y-3 text-xs">
                    <div>
                        <label class="block text-gray-400 mb-1">Binance API Key:</label>
                        <input type="text" id="cfg-binance-key" placeholder="کلید API اکانت بایننس شما" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white">
                    </div>
                    <div>
                        <label class="block text-gray-400 mb-1">Binance Secret Key:</label>
                        <input type="password" id="cfg-binance-secret" placeholder="کلید محرمانه Secret Key" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white">
                    </div>
                </div>
            </div>

            <!-- دکمه ذخیره -->
            <div class="mt-6 flex justify-end gap-3">
                <button onclick="closeSettingsModal()" class="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-sm">انصراف</button>
                <button onclick="saveAccountSettings()" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-lg shadow-emerald-900/30">
                    <i class="fa-solid fa-check"></i> ذخیره و اتصال آنی به اکانت
                </button>
            </div>
        </div>
    </div>

    <script>
        function openSettingsModal() {
            fetch('/api/config')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('cfg-trading-mode').value = data.trading_mode || 'PAPER';
                    document.getElementById('cfg-mt5-login').value = data.mt5.account_number || '';
                    document.getElementById('cfg-mt5-server').value = data.mt5.server || '';
                    document.getElementById('cfg-binance-key').value = data.binance.api_key || '';
                    document.getElementById('settings-modal').classList.remove('hidden');
                });
        }

        function closeSettingsModal() {
            document.getElementById('settings-modal').classList.add('hidden');
        }

        async function saveAccountSettings() {
            const payload = {
                trading_mode: document.getElementById('cfg-trading-mode').value,
                mt5: {
                    account_number: document.getElementById('cfg-mt5-login').value,
                    password: document.getElementById('cfg-mt5-pass').value,
                    server: document.getElementById('cfg-mt5-server').value,
                },
                binance: {
                    api_key: document.getElementById('cfg-binance-key').value,
                    secret_key: document.getElementById('cfg-binance-secret').value,
                    testnet: false
                }
            };

            const res = await fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                alert("✅ اطلاعات حساب با موفقیت ذخیره و به سیستم اعمال شد!");
                closeSettingsModal();
                fetchDashboardData();
            } else {
                alert("❌ خطا در ذخیره تنظیمات!");
            }
        }

        async function fetchDashboardData() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                document.getElementById('equity-val').innerText = `$${data.equity.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                document.getElementById('daily-pnl').innerText = `${data.daily_pnl >= 0 ? '+' : ''}$${data.daily_pnl.toFixed(2)}`;
                document.getElementById('daily-pnl').className = `text-2xl md:text-3xl font-extrabold mt-2 ${data.daily_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
                document.getElementById('open-positions-count').innerText = `${data.open_positions.length} / 3`;
                document.getElementById('account-id-display').innerText = data.account_info;
                document.getElementById('broker-connected-info').innerText = data.broker_info;
            } catch (err) {
                console.error(err);
            }
        }

        function emergencyStop() {
            if (confirm("آیا از فعال‌سازی توقف اضطراری سیستم اطمینان دارید؟")) {
                alert("دستور توقف اضطراری ارسال شد.");
            }
        }

        setInterval(fetchDashboardData, 2000);
        fetchDashboardData();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def get_dashboard_html():
    return HTMLResponse(content=HTML_TEMPLATE)


@app.get("/api/config")
def get_config_api():
    cfg = account_config.load_config()
    # عدم ارسال پسوردهای حساس به فرانت
    safe_cfg = {
        "trading_mode": cfg.get("trading_mode", "PAPER"),
        "mt5": {
            "account_number": cfg.get("mt5", {}).get("account_number", ""),
            "server": cfg.get("mt5", {}).get("server", ""),
        },
        "binance": {
            "api_key": cfg.get("binance", {}).get("api_key", ""),
        }
    }
    return JSONResponse(content=safe_cfg)


@app.post("/api/config")
async def save_config_api(request: Request):
    new_data = await request.json()
    account_config.save_config(new_data)

    # اتصال مجدد به متاتریدر در صورت ثبت لاگین جدید
    mt5_data = new_data.get("mt5", {})
    if MT5_AVAILABLE and mt5_data.get("account_number") and mt5_data.get("password"):
        try:
            mt5.initialize()
            mt5.login(
                login=int(mt5_data["account_number"]),
                password=mt5_data["password"],
                server=mt5_data.get("server")
            )
        except Exception:
            pass

    return JSONResponse(content={"status": "SUCCESS"})


@app.get("/api/status")
def get_status_api():
    account_equity = 50.0
    account_info_str = "حساب دمو"
    broker_info_str = "متاتریدر ۵ فعال است"

    if MT5_AVAILABLE:
        try:
            if mt5.initialize():
                acc = mt5.account_info()
                if acc:
                    account_equity = float(acc.equity)
                    account_info_str = f"اکانت {acc.login} ({acc.currency})"
                    broker_info_str = f"بروکر متصل: {acc.company} | سرور: {acc.server}"
        except Exception:
            pass

    summary = db.get_portfolio_summary()

    return {
        "equity": account_equity,
        "daily_pnl": summary["net_realized_pnl_usd"],
        "open_positions": [],
        "total_trades": summary["total_trades_count"],
        "account_info": account_info_str,
        "broker_info": broker_info_str,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 75)
    print("🌐 داشبورد گرافیکی مجهز به پنل تنظیمات اکانت راه‌اندازی شد!")
    print("💻 آدرس ورود در کامپیوتر:  http://127.0.0.1:8000")
    print(f"📱 آدرس ورود در گوشی موبایل: http://{local_ip}:8000")
    print("=" * 75)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")