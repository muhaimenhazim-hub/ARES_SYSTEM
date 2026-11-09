"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 11: MULTI-TENANT WEB DASHBOARD WITH USER AUTH & PER-USER ISOLATION
VERSION: 5.0 (CLOUD METAAPI & BINANCE COMPATIBLE)
================================================================================
"""

import os
import socket
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

import account_config
from ares_database import AresDatabaseManager

app = FastAPI(title="ARES AI MULTI-USER TRADING DASHBOARD")
db = AresDatabaseManager()


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
    <title>ARES AI TRADING SYSTEM — سامانه معاملات هوشمند</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; background-color: #0b0e14; color: #e2e8f0; }
        .card { background-color: #151b26; border: 1px solid #232d3f; border-radius: 0.75rem; }
        .glow-green { box-shadow: 0 0 15px rgba(16, 185, 129, 0.2); }
        .modal { background-color: rgba(0, 0, 0, 0.85); backdrop-filter: blur(6px); }
    </style>
</head>
<body class="p-4 md:p-6 min-h-screen flex flex-col justify-between">

    <!-- صفحه ورود و ثبت نام اختصاصی -->
    <div id="auth-container" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0b0e14]">
        <div class="card max-w-md w-full p-6 md:p-8 text-right border-gray-800 shadow-2xl">
            <div class="text-center mb-6">
                <div class="inline-block p-3 rounded-full bg-emerald-950/60 border border-emerald-800 mb-3">
                    <i class="fa-solid fa-robot text-3xl text-emerald-400"></i>
                </div>
                <h2 class="text-xl md:text-2xl font-bold text-white tracking-wider">ARES AI TRADING</h2>
                <p class="text-xs text-gray-400 mt-1">سامانه اختصاصی مدیریت معاملات هوشمند</p>
            </div>

            <!-- تب های ورود / ثبت نام -->
            <div class="flex border-b border-gray-800 mb-6">
                <button id="tab-login-btn" onclick="switchAuthTab('login')" class="flex-1 pb-3 text-sm font-bold text-emerald-400 border-b-2 border-emerald-400 transition">ورود به حساب</button>
                <button id="tab-register-btn" onclick="switchAuthTab('register')" class="flex-1 pb-3 text-sm font-bold text-gray-500 transition">ثبت‌نام کاربر جدید</button>
            </div>

            <div class="space-y-4 text-xs md:text-sm">
                <div>
                    <label class="block text-gray-400 mb-1">ایمیل یا شماره موبایل:</label>
                    <input type="text" id="auth-identifier" placeholder="مثال: user@gmail.com" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-white focus:outline-none focus:border-emerald-500">
                </div>
                <div>
                    <label class="block text-gray-400 mb-1">کلمه عبور:</label>
                    <input type="password" id="auth-password" placeholder="حداقل ۴ کاراکتر" class="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-white focus:outline-none focus:border-emerald-500">
                </div>
                <button id="auth-submit-btn" onclick="handleAuthSubmit()" class="w-full py-3 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-lg transition shadow-lg shadow-emerald-950/40">
                    ورود به پنل کاربری
                </button>
                <div id="auth-error-msg" class="text-red-400 text-xs text-center hidden"></div>
            </div>
        </div>
    </div>

    <!-- داشبورد اصلی -->
    <div id="main-dashboard" class="hidden">
        <header class="flex flex-wrap justify-between items-center mb-6 pb-4 border-b border-gray-800 gap-4">
            <div>
                <div class="flex items-center gap-3">
                    <div class="h-4 w-4 rounded-full bg-emerald-500 animate-pulse"></div>
                    <h1 class="text-xl md:text-2xl font-bold tracking-wider text-emerald-400">ARES AI TRADING SYSTEM</h1>
                    <span id="user-display-badge" class="text-xs bg-gray-800 text-gray-300 border border-gray-700 px-3 py-1 rounded-full font-mono">کاربر: ...</span>
                </div>
                <p class="text-gray-400 text-xs md:text-sm mt-1" id="broker-connected-info">در حال پایش اطلاعات حساب ابری...</p>
            </div>
            
            <div class="flex flex-wrap gap-2 items-center">
                <button id="btn-toggle-trading" onclick="toggleAutoTrading()" class="px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1.5 shadow-md">
                    <i class="fa-solid fa-play"></i> <span id="lbl-toggle-trading">شروع معامله خودکار</span>
                </button>
                
                <button onclick="disconnectBroker()" class="bg-red-950/40 border border-red-800 hover:bg-red-900 text-red-300 px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1">
                    <i class="fa-solid fa-unlink"></i> قطع ارتباط حساب
                </button>

                <button onclick="openSettingsModal()" class="bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1 shadow-md shadow-blue-900/30">
                    <i class="fa-solid fa-gear"></i> تنظیمات حساب
                </button>

                <button onclick="logoutUser()" class="bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1">
                    <i class="fa-solid fa-right-from-bracket"></i> خروج
                </button>
            </div>
        </header>

        <!-- کارت‌های مالی -->
        <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 md:gap-6 mb-8">
            <div class="card p-5 glow-green">
                <div class="text-gray-400 text-sm font-medium flex justify-between">
                    <span>موجودی واقعی حساب (Equity)</span>
                    <i class="fa-solid fa-wallet text-emerald-400"></i>
                </div>
                <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="equity-val">$0.00</div>
                <div class="text-xs text-gray-400 mt-2 font-medium" id="account-id-display">هیچ حسابی متصل نیست</div>
            </div>

            <div class="card p-5">
                <div class="text-gray-400 text-sm font-medium flex justify-between">
                    <span>سود محقق‌شده معاملات</span>
                    <i class="fa-solid fa-chart-line text-blue-400"></i>
                </div>
                <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="daily-pnl">+$0.00</div>
                <div class="text-xs text-gray-400 mt-2">محاسبه بر اساس معاملات بسته شده شما</div>
            </div>

            <div class="card p-5">
                <div class="text-gray-400 text-sm font-medium flex justify-between">
                    <span>پوزیشن‌های فعال</span>
                    <i class="fa-solid fa-layer-group text-purple-400"></i>
                </div>
                <div class="text-2xl md:text-3xl font-extrabold text-white mt-2" id="open-positions-count">0 / 3</div>
                <div class="text-xs text-gray-400 mt-2">سقف مجاز: حداکثر ۳ پوزیشن</div>
            </div>

            <div class="card p-5">
                <div class="text-gray-400 text-sm font-medium flex justify-between">
                    <span>افت سرمایه (Drawdown)</span>
                    <i class="fa-solid fa-shield-halved text-amber-400"></i>
                </div>
                <div class="text-2xl md:text-3xl font-extrabold text-emerald-400 mt-2">0.00%</div>
                <div class="text-xs text-gray-400 mt-2">سقف کنترل ریسک: 12%</div>
            </div>
        </div>

        <!-- جدول پوزیشن‌ها -->
        <div class="card p-4 md:p-6 mb-8">
            <h2 class="text-base font-bold text-gray-200 mb-4 flex items-center gap-2">
                <i class="fa-solid fa-bolt text-amber-400"></i> پوزیشن‌های باز اکانت شما
            </h2>
            <div class="overflow-x-auto">
                <table class="w-full text-right text-xs md:text-sm">
                    <thead class="text-gray-400 bg-gray-900/50 uppercase border-b border-gray-800">
                        <tr>
                            <th class="py-3 px-3">شناسه</th>
                            <th class="py-3 px-3">نماد</th>
                            <th class="py-3 px-3">جهت</th>
                            <th class="py-3 px-3">قیمت ورود</th>
                            <th class="py-3 px-3">حد ضرر (SL)</th>
                            <th class="py-3 px-3">حجم</th>
                            <th class="py-3 px-3">سود/زیان</th>
                            <th class="py-3 px-3">وضعیت</th>
                        </tr>
                    </thead>
                    <tbody id="open-trades-table" class="divide-y divide-gray-800">
                        <tr>
                            <td colspan="8" class="py-6 text-center text-gray-500">هیچ معامله بازی وجود ندارد.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- مودال تنظیمات -->
    <div id="settings-modal" class="fixed inset-0 modal flex items-center justify-center p-4 hidden z-50">
        <div class="bg-gray-900 border border-gray-700 rounded-xl max-w-xl w-full p-6 text-right max-h-[90vh] overflow-y-auto shadow-2xl">
            <div class="flex justify-between items-center pb-3 border-b border-gray-800">
                <h3 class="text-base font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-sliders text-blue-400"></i> اتصال حساب معاملاتی شما
                </h3>
                <button onclick="closeSettingsModal()" class="text-gray-400 hover:text-white text-xl">&times;</button>
            </div>

            <div class="mt-4">
                <label class="block text-xs font-bold text-gray-400 mb-1">حالت معامله:</label>
                <select id="cfg-trading-mode" class="w-full bg-gray-800 border border-gray-700 rounded-lg p-2.5 text-xs text-white">
                    <option value="PAPER">آزمایشی (Paper Trading)</option>
                    <option value="LIVE">حساب واقعی لایو (Live Trading)</option>
                </select>
            </div>

            <!-- متاتریدر ۵ -->
            <div class="mt-4 p-4 rounded-lg bg-gray-800/40 border border-gray-700/60 space-y-2.5 text-xs">
                <h4 class="font-bold text-emerald-400 flex items-center gap-1.5"><i class="fa-solid fa-chart-line"></i> متاتریدر ۵ (فارکس و انس طلا)</h4>
                <div>
                    <label class="block text-gray-400 mb-1">شماره حساب (Login Number):</label>
                    <input type="text" id="cfg-mt5-login" placeholder="مثال: 115293699" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white font-mono">
                </div>
                <div>
                    <label class="block text-gray-400 mb-1">رمز عبور حساب (Password):</label>
                    <input type="password" id="cfg-mt5-pass" placeholder="Password" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white font-mono">
                </div>
                <div>
                    <label class="block text-gray-400 mb-1">نام سرور بروکر (Server Name):</label>
                    <input type="text" id="cfg-mt5-server" placeholder="مثال: MetaQuotes-Demo" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white font-mono">
                </div>
            </div>

            <!-- بایننس -->
            <div class="mt-4 p-4 rounded-lg bg-gray-800/40 border border-amber-900/40 space-y-2.5 text-xs">
                <h4 class="font-bold text-amber-400 flex items-center gap-1.5"><i class="fa-brands fa-bitcoin"></i> صرافی بایننس (کریپتو فیوچرز)</h4>
                <div>
                    <label class="block text-gray-400 mb-1">Binance API Key:</label>
                    <input type="text" id="cfg-binance-key" placeholder="API Key" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white font-mono">
                </div>
                <div>
                    <label class="block text-gray-400 mb-1">Binance Secret Key:</label>
                    <input type="password" id="cfg-binance-secret" placeholder="Secret Key" class="w-full bg-gray-800 border border-gray-700 rounded p-2 text-white font-mono">
                </div>
            </div>

            <div class="mt-6 flex justify-end gap-3">
                <button onclick="closeSettingsModal()" class="px-4 py-2 bg-gray-800 text-gray-300 rounded-lg text-xs">انصراف</button>
                <button onclick="saveAccountSettings()" class="px-5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold">
                    ذخیره و اتصال
                </button>
            </div>
        </div>
    </div>

    <script>
        let currentUser = JSON.parse(localStorage.getItem('ares_user') || 'null');
        let currentAuthMode = 'login';

        function switchAuthTab(mode) {
            currentAuthMode = mode;
            const loginBtn = document.getElementById('tab-login-btn');
            const regBtn = document.getElementById('tab-register-btn');
            const submitBtn = document.getElementById('auth-submit-btn');

            if (mode === 'login') {
                loginBtn.className = "flex-1 pb-3 text-sm font-bold text-emerald-400 border-b-2 border-emerald-400 transition";
                regBtn.className = "flex-1 pb-3 text-sm font-bold text-gray-500 transition";
                submitBtn.innerText = "ورود به پنل کاربری";
            } else {
                regBtn.className = "flex-1 pb-3 text-sm font-bold text-emerald-400 border-b-2 border-emerald-400 transition";
                loginBtn.className = "flex-1 pb-3 text-sm font-bold text-gray-500 transition";
                submitBtn.innerText = "ثبت‌نام و ایجاد حساب";
            }
        }

        async function handleAuthSubmit() {
            const identifier = document.getElementById('auth-identifier').value.trim();
            const password = document.getElementById('auth-password').value.trim();
            const errBox = document.getElementById('auth-error-msg');

            if (!identifier || !password) {
                errBox.innerText = "لطفاً ایمیل/موبایل و کلمه عبور را وارد کنید.";
                errBox.classList.remove('hidden');
                return;
            }

            const endpoint = currentAuthMode === 'login' ? '/api/auth/login' : '/api/auth/register';
            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({identifier, password})
                });
                const data = await res.json();
                if (res.ok) {
                    localStorage.setItem('ares_user', JSON.stringify(data));
                    currentUser = data;
                    document.getElementById('auth-container').classList.add('hidden');
                    document.getElementById('main-dashboard').classList.remove('hidden');
                    initDashboard();
                } else {
                    errBox.innerText = data.detail || "خطا در عملیات ورود/ثبت‌نام";
                    errBox.classList.remove('hidden');
                }
            } catch (err) {
                errBox.innerText = "ارتباط با سرور برقرار نشد.";
                errBox.classList.remove('hidden');
            }
        }

        function logoutUser() {
            localStorage.removeItem('ares_user');
            currentUser = null;
            location.reload();
        }

        function initDashboard() {
            if (!currentUser) return;
            document.getElementById('user-display-badge').innerText = `👤 کاربر: ${currentUser.identifier}`;
            fetchUserStatus();
            setInterval(fetchUserStatus, 2500);
        }

        async function fetchUserStatus() {
            if (!currentUser) return;
            try {
                const res = await fetch('/api/user/status', {
                    headers: {'X-User-Id': currentUser.user_id}
                });
                if (!res.ok) {
                    if (res.status === 401) logoutUser();
                    return;
                }
                const data = await res.json();
                document.getElementById('equity-val').innerText = `$${data.equity.toFixed(2)}`;
                document.getElementById('daily-pnl').innerText = `${data.daily_pnl >= 0 ? '+' : ''}$${data.daily_pnl.toFixed(2)}`;
                document.getElementById('daily-pnl').className = `text-2xl md:text-3xl font-extrabold mt-2 ${data.daily_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`;
                document.getElementById('open-positions-count').innerText = `${data.open_positions_count} / 3`;
                document.getElementById('account-id-display').innerText = data.account_info;
                document.getElementById('broker-connected-info').innerText = data.broker_info;

                const btnToggle = document.getElementById('btn-toggle-trading');
                const lblToggle = document.getElementById('lbl-toggle-trading');
                if (data.is_auto_trading) {
                    btnToggle.className = "bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1.5 shadow-md shadow-emerald-950/40";
                    lblToggle.innerText = "معامله خودکار فعال است (کلیک برای توقف)";
                } else {
                    btnToggle.className = "bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 px-3 py-2 rounded-lg font-bold text-xs transition flex items-center gap-1.5 shadow-md";
                    lblToggle.innerText = "اجازه معامله به ربات (شروع معامله)";
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function toggleAutoTrading() {
            if (!currentUser) return;
            const res = await fetch('/api/user/toggle-trading', {
                method: 'POST',
                headers: {'X-User-Id': currentUser.user_id}
            });
            const data = await res.json();
            alert(data.message);
            fetchUserStatus();
        }

        async function disconnectBroker() {
            if (!currentUser) return;
            if (!confirm("آیا از قطع ارتباط کامل حساب خود و توقف تمام معاملات اطمینان دارید؟")) return;
            const res = await fetch('/api/user/disconnect', {
                method: 'POST',
                headers: {'X-User-Id': currentUser.user_id}
            });
            const data = await res.json();
            alert(data.message);
            fetchUserStatus();
        }

        function openSettingsModal() {
            if (!currentUser) return;
            fetch('/api/user/config', {
                headers: {'X-User-Id': currentUser.user_id}
            })
            .then(r => r.json())
            .then(data => {
                document.getElementById('cfg-trading-mode').value = data.trading_mode || 'PAPER';
                document.getElementById('cfg-mt5-login').value = data.mt5_login || '';
                document.getElementById('cfg-mt5-server').value = data.mt5_server || '';
                document.getElementById('cfg-binance-key').value = data.binance_api_key || '';
                document.getElementById('settings-modal').classList.remove('hidden');
            });
        }

        function closeSettingsModal() {
            document.getElementById('settings-modal').classList.add('hidden');
        }

        async function saveAccountSettings() {
            if (!currentUser) return;
            const payload = {
                trading_mode: document.getElementById('cfg-trading-mode').value,
                mt5_login: document.getElementById('cfg-mt5-login').value,
                mt5_pass: document.getElementById('cfg-mt5-pass').value,
                mt5_server: document.getElementById('cfg-mt5-server').value,
                binance_api_key: document.getElementById('cfg-binance-key').value,
                binance_secret_key: document.getElementById('cfg-binance-secret').value,
            };

            const res = await fetch('/api/user/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': currentUser.user_id
                },
                body: JSON.stringify(payload)
            });

            const data = await res.json();
            if (res.ok) {
                alert(data.message);
                closeSettingsModal();
                fetchUserStatus();
            } else {
                alert("خطا در ذخیره مشخصات");
            }
        }

        if (currentUser && currentUser.user_id) {
            document.getElementById('auth-container').classList.add('hidden');
            document.getElementById('main-dashboard').classList.remove('hidden');
            initDashboard();
        }
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def get_index():
    return HTMLResponse(content=HTML_TEMPLATE)


@app.post("/api/auth/register")
async def register_api(request: Request):
    data = await request.json()
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()

    res = db.register_user(identifier, password)
    if not res:
        raise HTTPException(status_code=400, detail="این شماره/ایمیل قبلاً ثبت شده یا کلمه عبور کوتاه است.")
    return res


@app.post("/api/auth/login")
async def login_api(request: Request):
    data = await request.json()
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()

    user = db.authenticate_user(identifier, password)
    if not user:
        raise HTTPException(status_code=401, detail="اطلاعات ورود یا کلمه عبور نادرست است.")
    return user


@app.get("/api/user/status")
async def get_user_status_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")

    user_cfg = db.get_user_broker_config(x_user_id)
    try:
        equity, acc_info, broker_info, is_conn = account_config.fetch_user_live_balance(user_cfg)
    except Exception:
        equity, acc_info, broker_info, is_conn = 0.0, "در حال همگام‌سازی", "برقراری ارتباط ابری...", False

    summary = db.get_portfolio_summary(user_id=x_user_id)

    return {
        "equity": equity,
        "daily_pnl": summary.get("net_realized_pnl_usd", 0.0),
        "open_positions_count": summary.get("open_trades_count", 0),
        "account_info": acc_info,
        "broker_info": broker_info,
        "is_connected": is_conn,
        "is_auto_trading": bool(user_cfg.get("is_auto_trading", 0)),
    }


@app.get("/api/user/config")
def get_user_config_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    cfg = db.get_user_broker_config(x_user_id)
    return {
        "trading_mode": cfg.get("trading_mode", "PAPER"),
        "mt5_login": cfg.get("mt5_login", ""),
        "mt5_server": cfg.get("mt5_server", ""),
        "binance_api_key": cfg.get("binance_api_key", ""),
    }


@app.post("/api/user/config")
async def save_user_config_api(request: Request, x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")

    new_cfg = await request.json()
    db.save_user_broker_config(x_user_id, new_cfg)
    return {"status": "SUCCESS", "message": "تنظیمات حساب شما با موفقیت ذخیره شد."}


@app.post("/api/user/toggle-trading")
def toggle_trading_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    new_state = db.toggle_auto_trading(x_user_id)
    status_txt = "فعال شد. ربات روی حساب شما معامله خواهد کرد." if new_state else "متوقف شد. هیچ معامله جدیدی باز نمی‌شود."
    return {"status": "SUCCESS", "is_auto_trading": new_state, "message": f"معامله خودکار {status_txt}"}


@app.post("/api/user/disconnect")
def disconnect_broker_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    db.disconnect_broker(x_user_id)
    return {"status": "SUCCESS", "message": "ارتباط با حساب متاتریدر/صرافی با موفقیت قطع شد."}


if __name__ == "__main__":
    local_ip = get_local_ip()
    print("=" * 75)
    print("داشبورد چندکاربره سیستم ARES فعال شد.")
    print(f"آدرس ورود: http://{local_ip}:8000")
    print("=" * 75)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")