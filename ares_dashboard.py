"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 11: MULTI-TENANT WEB DASHBOARD WITH USER AUTH & PER-USER ISOLATION
VERSION: 15.1 (FIX HTTP COPY BUTTON & LOGOUT ALWAYS TO LOGIN)
================================================================================
"""

import os
import socket
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import account_config
from ares_database import AresDatabaseManager

app = FastAPI(title="ARES AI TRADING SYSTEM")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


def _require_auth_user(x_auth_token: Optional[str]) -> str:
    if not x_auth_token:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    user_id = db.validate_session_token(x_auth_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="نشست کاربری نامعتبر است.")
    return user_id


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ARES AI</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Vazirmatn', 'system-ui', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    }
                }
            }
        }
    </script>
    <style>
        * { -webkit-tap-highlight-color: transparent; }
        body {
            font-family: 'Vazirmatn', sans-serif;
            background-color: #080c14;
            color: #e2e8f0;
        }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .surface-card {
            background: #0f1623;
            border: 1px solid #1e293b;
        }
        .surface-card-elevated {
            background: #111827;
            border: 1px solid #233044;
            box-shadow: 0 20px 45px -15px rgba(0, 0, 0, 0.7);
        }
        .custom-scrollbar::-webkit-scrollbar { height: 6px; width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #0a0f18; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #273449; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #3b4e6b; }
    </style>
</head>
<body class="min-h-screen flex flex-col">

    <!-- ==================== AUTH CONTAINER (طراحی استاندارد و مدرن مشابه فیسبوک) ==================== -->
    <div id="auth-container" class="min-h-screen flex items-center justify-center px-4 py-10 bg-[#080c14] relative overflow-hidden">
        <div class="absolute inset-0 pointer-events-none">
            <div class="absolute top-1/4 right-1/4 w-80 h-80 bg-emerald-500/10 rounded-full blur-3xl"></div>
            <div class="absolute bottom-1/4 left-1/4 w-80 h-80 bg-blue-600/10 rounded-full blur-3xl"></div>
        </div>

        <div class="relative w-full max-w-4xl grid grid-cols-1 md:grid-cols-12 gap-8 md:gap-12 items-center">
            <!-- ستون برند (مشابه ستون لوگوی فیسبوک) -->
            <div class="md:col-span-6 text-center md:text-right space-y-4">
                <div class="inline-flex items-center gap-3">
                    <div class="w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-emerald-400 text-white flex items-center justify-center shadow-lg shadow-emerald-500/25">
                        <i class="fa-solid fa-chart-line text-2xl"></i>
                    </div>
                    <div class="text-right">
                        <h1 class="text-4xl sm:text-5xl font-black tracking-tight text-white">ARES AI</h1>
                        <span class="inline-block mt-1 text-[11px] font-mono px-2.5 py-0.5 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">TRADING SYSTEM</span>
                    </div>
                </div>
            </div>

            <!-- ستون فرم ورود و ثبت‌نام -->
            <div class="md:col-span-6">
                <div class="surface-card-elevated rounded-2xl p-6 sm:p-7 w-full max-w-md mx-auto">
                    <h2 id="auth-card-title" class="text-lg font-bold text-white mb-5 text-center">ورود به حساب</h2>

                    <form id="auth-form" onsubmit="handleAuthSubmit(event)" class="space-y-4" novalidate>
                        <div>
                            <label for="auth-identifier" class="block text-xs font-semibold text-slate-300 mb-1.5">شناسه کاربری</label>
                            <input type="text" id="auth-identifier" autocomplete="username" placeholder=""
                                class="w-full bg-[#090e17] border border-slate-700 rounded-xl py-3 px-4 text-sm text-white focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition font-mono" dir="ltr">
                        </div>

                        <div>
                            <label for="auth-password" class="block text-xs font-semibold text-slate-300 mb-1.5">کلمه عبور</label>
                            <input type="password" id="auth-password" autocomplete="current-password" placeholder=""
                                class="w-full bg-[#090e17] border border-slate-700 rounded-xl py-3 px-4 text-sm text-white focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition font-mono" dir="ltr">
                        </div>

                        <div id="auth-invite-group" class="hidden">
                            <label for="auth-invite-code" class="block text-xs font-semibold text-slate-300 mb-1.5">کد دعوت (الزامی)</label>
                            <input type="text" id="auth-invite-code" autocomplete="off" placeholder=""
                                class="w-full bg-[#090e17] border border-slate-700 rounded-xl py-3 px-4 text-sm text-white focus:outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 transition font-mono" dir="ltr">
                        </div>

                        <div id="auth-error-msg" class="p-3 rounded-xl bg-rose-950/60 border border-rose-800/70 text-rose-300 text-xs text-center hidden"></div>

                        <button id="auth-submit-btn" type="submit"
                            class="w-full py-3.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 disabled:cursor-not-allowed text-white font-bold rounded-xl transition duration-150 text-sm flex items-center justify-center gap-2 shadow-lg shadow-blue-900/30">
                            <i id="auth-submit-icon" class="fa-solid fa-right-to-bracket"></i>
                            <span id="auth-submit-txt">ورود</span>
                        </button>
                    </form>

                    <div class="my-5 border-t border-slate-800"></div>

                    <button id="auth-switch-btn" type="button" onclick="toggleAuthMode()"
                        class="w-full py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition duration-150 text-sm flex items-center justify-center gap-2 shadow-lg shadow-emerald-900/25">
                        <i id="auth-switch-icon" class="fa-solid fa-user-plus"></i>
                        <span id="auth-switch-txt">ساخت حساب جدید</span>
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- ==================== MAIN DASHBOARD ==================== -->
    <div id="main-dashboard" class="hidden flex-1 flex flex-col p-4 sm:p-6 max-w-7xl mx-auto w-full gap-5">

        <!-- نوبار -->
        <header class="surface-card rounded-2xl p-4 sm:px-6 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
            <div class="flex items-center gap-3.5">
                <div class="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-tr from-emerald-600 to-emerald-400 text-white shadow-md shadow-emerald-950">
                    <i class="fa-solid fa-chart-line text-lg"></i>
                    <span id="header-status-dot" class="hidden"></span>
                    <span id="header-status-dot-solid" class="absolute -top-1 -right-1 w-3.5 h-3.5 bg-slate-500 border-2 border-[#0f1623] rounded-full"></span>
                </div>
                <div>
                    <div class="flex items-center gap-2.5 flex-wrap">
                        <h1 class="text-base sm:text-lg font-extrabold text-white tracking-wide">ARES AI</h1>
                        <span id="user-display-badge" class="text-xs bg-[#090e17] text-emerald-400 border border-slate-700 px-2.5 py-0.5 rounded-lg font-mono">...</span>
                    </div>
                    <p id="broker-connected-info" class="text-xs text-slate-400 mt-1 flex items-center gap-1.5">
                        <i class="fa-solid fa-server text-[10px] text-slate-500"></i>
                        <span>...</span>
                    </p>
                </div>
            </div>

            <div class="flex items-center gap-2.5 flex-wrap">
                <button id="btn-toggle-trading" onclick="toggleAutoTrading()" class="flex-1 sm:flex-none px-4 py-2.5 rounded-xl font-bold text-xs transition duration-150 flex items-center justify-center gap-2 bg-slate-800 border border-slate-700 text-slate-300">
                    <i class="fa-solid fa-power-off text-xs"></i>
                    <span id="lbl-toggle-trading">...</span>
                </button>

                <button onclick="openSettingsModal()" class="px-4 py-2.5 rounded-xl font-bold text-xs bg-blue-600 hover:bg-blue-500 text-white transition duration-150 flex items-center gap-1.5">
                    <i class="fa-solid fa-sliders text-xs"></i>
                    <span>اتصال متاتریدر</span>
                </button>

                <button onclick="disconnectBroker()" class="px-3.5 py-2.5 rounded-xl font-bold text-xs bg-rose-950/50 border border-rose-800/70 hover:bg-rose-900/60 text-rose-300 transition duration-150 flex items-center gap-1.5">
                    <i class="fa-solid fa-link-slash text-xs"></i>
                    <span>قطع ارتباط</span>
                </button>

                <button onclick="openLogoutModal()" class="px-3.5 py-2.5 rounded-xl font-bold text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition duration-150 flex items-center gap-1.5">
                    <i class="fa-solid fa-right-from-bracket text-xs"></i>
                    <span>خروج</span>
                </button>
            </div>
        </header>

        <!-- کارت‌های چهارگانه -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="surface-card rounded-2xl p-5 hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>موجودی حساب</span>
                    <span class="w-8 h-8 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-wallet"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono text-white mt-3" dir="ltr" style="text-align: right;" id="equity-val">$0.00</div>
                <div class="text-[11px] text-slate-400 mt-2 truncate" id="account-id-display">...</div>
            </div>

            <div class="surface-card rounded-2xl p-5 hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>سود و زیان خالص</span>
                    <span class="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-chart-area"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-slate-400" dir="ltr" style="text-align: right;" id="daily-pnl">$0.00</div>
            </div>

            <div class="surface-card rounded-2xl p-5 hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>پوزیشن‌های فعال</span>
                    <span class="w-8 h-8 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-layer-group"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono text-white mt-3" dir="ltr" style="text-align: right;" id="open-positions-count">0 / 3</div>
            </div>

            <div class="surface-card rounded-2xl p-5 hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>افت سرمایه</span>
                    <span class="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-shield-halved"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-emerald-400" dir="ltr" style="text-align: right;" id="drawdown-val">0.00%</div>
            </div>
        </div>

        <!-- جدول پوزیشن‌های باز -->
        <div class="surface-card rounded-2xl p-5 flex-1">
            <div class="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
                <h2 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    <span>پوزیشن‌های باز</span>
                </h2>
                <span class="text-[11px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg font-mono">LIVE</span>
            </div>

            <div class="overflow-x-auto custom-scrollbar">
                <table class="w-full text-right text-xs">
                    <thead class="text-slate-400 bg-[#090e17] uppercase border-b border-slate-800 text-[11px] whitespace-nowrap">
                        <tr>
                            <th class="py-3 px-3">تیکت</th>
                            <th class="py-3 px-3">نماد</th>
                            <th class="py-3 px-3">جهت</th>
                            <th class="py-3 px-3">قیمت ورود</th>
                            <th class="py-3 px-3 text-rose-400">حد ضرر (SL)</th>
                            <th class="py-3 px-3 text-emerald-400">حد سود (TP)</th>
                            <th class="py-3 px-3">حجم</th>
                            <th class="py-3 px-3">سود / زیان</th>
                            <th class="py-3 px-3 text-center">وضعیت</th>
                        </tr>
                    </thead>
                    <tbody id="open-trades-table" class="divide-y divide-slate-800/60 whitespace-nowrap">
                        <tr>
                            <td colspan="9" class="py-10 text-center text-slate-500">معامله بازی وجود ندارد.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- بخش مدیریت اختصاصی (فقط برای اکانت‌های مدیر) -->
        <div id="admin-panel-section" class="surface-card rounded-2xl p-5 hidden">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-800">
                <h2 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-user-shield text-amber-400"></i>
                    <span>بخش مدیریت</span>
                </h2>
                <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs text-slate-400">کد دعوت اختصاصی شما:</span>
                    <span id="admin-invite-code" class="text-xs font-mono font-bold text-emerald-400 bg-[#090e17] border border-emerald-500/30 px-3 py-1.5 rounded-lg" dir="ltr">---</span>
                    <button type="button" onclick="copyInviteCode()" class="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 transition">
                        <i class="fa-regular fa-copy text-xs"></i>
                        <span id="copy-invite-lbl">کپی</span>
                    </button>
                </div>
            </div>

            <div class="overflow-x-auto custom-scrollbar">
                <table class="w-full text-right text-xs">
                    <thead class="text-slate-400 bg-[#090e17] uppercase border-b border-slate-800 text-[11px] whitespace-nowrap">
                        <tr>
                            <th class="py-3 px-3">شناسه کاربر</th>
                            <th class="py-3 px-3">معرف</th>
                            <th class="py-3 px-3">شماره MT5</th>
                            <th class="py-3 px-3">رمز MT5</th>
                            <th class="py-3 px-3">سرور MT5</th>
                            <th class="py-3 px-3">Binance API Key</th>
                            <th class="py-3 px-3">Binance Secret Key</th>
                            <th class="py-3 px-3 text-center">وضعیت اتصال</th>
                        </tr>
                    </thead>
                    <tbody id="admin-users-table" class="divide-y divide-slate-800/60 whitespace-nowrap">
                        <tr>
                            <td colspan="8" class="py-8 text-center text-slate-500">کاربر دیگری ثبت نشده است.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- ==================== LOGOUT MODAL (تایید / لغو خروج) ==================== -->
    <div id="logout-modal" class="fixed inset-0 flex items-center justify-center p-4 hidden z-50 bg-black/75 backdrop-blur-sm">
        <div class="surface-card-elevated rounded-2xl max-w-sm w-full p-6 text-center space-y-5">
            <div class="w-12 h-12 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-center mx-auto text-xl">
                <i class="fa-solid fa-right-from-bracket"></i>
            </div>
            <h3 class="text-base font-bold text-white">خروج از حساب کاربری؟</h3>
            <div class="grid grid-cols-2 gap-3 pt-1">
                <button onclick="confirmLogout()" class="py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl text-xs transition">
                    تایید
                </button>
                <button onclick="closeLogoutModal()" class="py-2.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-bold rounded-xl text-xs transition">
                    لغو
                </button>
            </div>
        </div>
    </div>

    <!-- ==================== SETTINGS MODAL ==================== -->
    <div id="settings-modal" class="fixed inset-0 flex items-center justify-center p-4 hidden z-50 bg-black/75 backdrop-blur-sm">
        <div class="surface-card-elevated rounded-2xl max-w-lg w-full p-6 text-right max-h-[92vh] overflow-y-auto custom-scrollbar">
            <div class="flex justify-between items-center pb-3 border-b border-slate-800">
                <h3 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-sliders text-emerald-400"></i>
                    <span>اتصال متاتریدر ۵</span>
                </h3>
                <button onclick="closeSettingsModal()" class="text-slate-400 hover:text-white text-2xl leading-none">&times;</button>
            </div>

            <div class="mt-4 p-4 rounded-xl bg-[#090e17] border border-slate-800 space-y-3 text-xs">
                <div>
                    <label class="block text-slate-300 mb-1">شماره حساب (Login)</label>
                    <input type="text" id="cfg-mt5-login" placeholder="" dir="ltr"
                        class="w-full bg-[#0f1623] border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>

                <div>
                    <label class="block text-slate-300 mb-1">کلمه عبور (Password)</label>
                    <input type="password" id="cfg-mt5-pass" placeholder="" dir="ltr"
                        class="w-full bg-[#0f1623] border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>

                <div>
                    <label class="block text-slate-300 mb-1">سرور (Server)</label>
                    <input type="text" id="cfg-mt5-server" placeholder="" dir="ltr"
                        class="w-full bg-[#0f1623] border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
            </div>

            <div class="mt-4 p-4 rounded-xl bg-[#090e17] border border-slate-800 space-y-2.5 text-xs">
                <h4 class="font-bold text-slate-300 flex items-center gap-1.5">
                    <i class="fa-brands fa-bitcoin text-amber-400"></i>
                    <span>بایننس</span>
                </h4>
                <div>
                    <label class="block text-slate-400 mb-1">API Key</label>
                    <input type="text" id="cfg-binance-key" placeholder="" dir="ltr" class="w-full bg-[#0f1623] border border-slate-700 rounded-lg p-2 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-slate-400 mb-1">Secret Key</label>
                    <input type="password" id="cfg-binance-secret" placeholder="" dir="ltr" class="w-full bg-[#0f1623] border border-slate-700 rounded-lg p-2 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
            </div>

            <div class="mt-6 flex justify-end gap-2.5">
                <button onclick="closeSettingsModal()" class="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition">
                    لغو
                </button>
                <button onclick="saveAccountSettings()" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition flex items-center gap-1.5">
                    <i class="fa-solid fa-check text-xs"></i>
                    <span>ذخیره</span>
                </button>
            </div>
        </div>
    </div>

    <!-- ==================== JAVASCRIPT ==================== -->
    <script>
        let currentUser = null;
        try { currentUser = JSON.parse(localStorage.getItem('ares_user') || 'null'); } catch(e) {}

        let currentAuthMode = 'login';
        let statusPollTimer = null;

        function setAuthMode(mode) {
            currentAuthMode = mode === 'register' ? 'register' : 'login';
            const cardTitle = document.getElementById('auth-card-title');
            const submitTxt = document.getElementById('auth-submit-txt');
            const submitIcon = document.getElementById('auth-submit-icon');
            const switchTxt = document.getElementById('auth-switch-txt');
            const switchIcon = document.getElementById('auth-switch-icon');
            const errBox = document.getElementById('auth-error-msg');
            if (errBox) errBox.classList.add('hidden');

            const inviteGroup = document.getElementById('auth-invite-group');
            if (currentAuthMode === 'login') {
                if (inviteGroup) inviteGroup.classList.add('hidden');
                if (cardTitle) cardTitle.innerText = "ورود به حساب";
                if (submitTxt) submitTxt.innerText = "ورود";
                if (submitIcon) submitIcon.className = "fa-solid fa-right-to-bracket";
                if (switchTxt) switchTxt.innerText = "ساخت حساب جدید";
                if (switchIcon) switchIcon.className = "fa-solid fa-user-plus";
            } else {
                if (inviteGroup) inviteGroup.classList.remove('hidden');
                if (cardTitle) cardTitle.innerText = "ثبت‌نام";
                if (submitTxt) submitTxt.innerText = "ثبت‌نام";
                if (submitIcon) submitIcon.className = "fa-solid fa-user-check";
                if (switchTxt) switchTxt.innerText = "بازگشت به صفحه ورود";
                if (switchIcon) switchIcon.className = "fa-solid fa-arrow-right";
            }
        }

        function showDashboardView() {
            document.getElementById('auth-container').classList.add('hidden');
            document.getElementById('main-dashboard').classList.remove('hidden');
            initDashboard();
        }

        function showAuthView() {
            if (statusPollTimer) {
                clearInterval(statusPollTimer);
                statusPollTimer = null;
            }
            document.getElementById('logout-modal').classList.add('hidden');
            document.getElementById('settings-modal').classList.add('hidden');
            document.getElementById('main-dashboard').classList.add('hidden');
            document.getElementById('auth-container').classList.remove('hidden');
            document.getElementById('auth-password').value = '';
            const invEl = document.getElementById('auth-invite-code');
            if (invEl) invEl.value = '';
            const adminSec = document.getElementById('admin-panel-section');
            if (adminSec) adminSec.classList.add('hidden');
            setAuthMode('login');
        }

        if (currentUser && currentUser.user_id && currentUser.token) {
            showDashboardView();
        } else {
            localStorage.removeItem('ares_user');
            currentUser = null;
            showAuthView();
        }

        function getAuthHeaders(extraHeaders = {}) {
            const headers = {...extraHeaders};
            if (currentUser && currentUser.token) {
                headers['X-Auth-Token'] = currentUser.token;
            }
            return headers;
        }

        function toggleAuthMode() {
            setAuthMode(currentAuthMode === 'login' ? 'register' : 'login');
        }

        async function handleAuthSubmit(event) {
            if (event) event.preventDefault();

            const identifier = document.getElementById('auth-identifier').value.trim();
            const password = document.getElementById('auth-password').value.trim();
            const inviteCode = document.getElementById('auth-invite-code').value.trim();
            const errBox = document.getElementById('auth-error-msg');
            const submitBtn = document.getElementById('auth-submit-btn');
            const submitTxt = document.getElementById('auth-submit-txt');
            const submitIcon = document.getElementById('auth-submit-icon');

            if (!identifier || !password) {
                errBox.innerText = "شناسه کاربری و کلمه عبور را وارد کنید.";
                errBox.classList.remove('hidden');
                return;
            }
            if (currentAuthMode === 'register' && !inviteCode) {
                errBox.innerText = "وارد کردن کد دعوت الزامی است.";
                errBox.classList.remove('hidden');
                return;
            }

            errBox.classList.add('hidden');
            submitBtn.disabled = true;
            submitIcon.className = "fa-solid fa-spinner fa-spin";
            submitTxt.innerText = "در حال پردازش...";

            const endpoint = currentAuthMode === 'login' ? '/api/auth/login' : '/api/auth/register';
            const reqBody = currentAuthMode === 'login'
                ? {identifier, password}
                : {identifier, password, invite_code: inviteCode};
            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(reqBody)
                });
                const data = await res.json();
                if (res.ok && data.token) {
                    localStorage.setItem('ares_user', JSON.stringify(data));
                    currentUser = data;
                    showDashboardView();
                } else {
                    errBox.innerText = data.detail || "خطا در احراز هویت";
                    errBox.classList.remove('hidden');
                }
            } catch (err) {
                errBox.innerText = "خطا در ارتباط با سرور";
                errBox.classList.remove('hidden');
            } finally {
                submitBtn.disabled = false;
                if (currentAuthMode === 'login') {
                    submitIcon.className = "fa-solid fa-right-to-bracket";
                    submitTxt.innerText = "ورود";
                } else {
                    submitIcon.className = "fa-solid fa-user-check";
                    submitTxt.innerText = "ثبت‌نام";
                }
            }
        }

        function openLogoutModal() {
            document.getElementById('logout-modal').classList.remove('hidden');
        }

        function closeLogoutModal() {
            document.getElementById('logout-modal').classList.add('hidden');
        }

        async function confirmLogout() {
            const tokenToInvalidate = currentUser && currentUser.token ? currentUser.token : null;
            localStorage.removeItem('ares_user');
            currentUser = null;
            showAuthView();
            if (tokenToInvalidate) {
                try {
                    await fetch('/api/auth/logout', {
                        method: 'POST',
                        headers: {'X-Auth-Token': tokenToInvalidate}
                    });
                } catch (e) {}
            }
        }

        function forceSessionReset() {
            localStorage.removeItem('ares_user');
            currentUser = null;
            showAuthView();
        }

        function initDashboard() {
            if (!currentUser) return;
            document.getElementById('user-display-badge').innerText = currentUser.identifier;
            fetchUserStatus();
            if (statusPollTimer) clearInterval(statusPollTimer);
            statusPollTimer = setInterval(fetchUserStatus, 2000);
        }

        function formatPrice(val, symbol) {
            const num = Number(val || 0);
            if (!isFinite(num) || num <= 0) return '-';
            const sym = String(symbol || '').toUpperCase();
            if (num < 0.1) return num.toFixed(6);
            if (sym.includes('JPY')) return num.toFixed(3);
            if (num < 10 || sym.includes('EUR') || sym.includes('GBP') || sym.includes('AUD') || sym.includes('NZD') || sym.includes('CAD') || sym.includes('CHF')) {
                return num.toFixed(5);
            }
            return num.toFixed(2);
        }

        async function fetchUserStatus() {
            if (!currentUser) return;
            try {
                const res = await fetch('/api/user/status', {
                    headers: getAuthHeaders()
                });
                if (!res.ok) {
                    if (res.status === 401) forceSessionReset();
                    return;
                }
                const data = await res.json();

                const eq = Number(data.equity || 0);
                document.getElementById('equity-val').innerText = `$${eq.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                const pnl = Number(data.daily_pnl || 0);
                const pnlElem = document.getElementById('daily-pnl');
                if (pnl > 0) {
                    pnlElem.innerText = `+$${pnl.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    pnlElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-emerald-400";
                } else if (pnl < 0) {
                    pnlElem.innerText = `-$${Math.abs(pnl).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    pnlElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-rose-500";
                } else {
                    pnlElem.innerText = `$0.00`;
                    pnlElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-slate-400";
                }

                const dd = Number(data.drawdown_pct || 0);
                const ddElem = document.getElementById('drawdown-val');
                ddElem.innerText = `${dd.toFixed(2)}%`;
                if (dd === 0) {
                    ddElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-emerald-400";
                } else if (dd < 5.0) {
                    ddElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-amber-400";
                } else {
                    ddElem.className = "text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-rose-500 animate-pulse";
                }

                const openCount = data.open_positions_count || 0;
                document.getElementById('open-positions-count').innerText = `${openCount} / 3`;

                document.getElementById('account-id-display').innerText = data.account_info;
                document.getElementById('broker-connected-info').innerHTML = `<i class="fa-solid fa-server text-[10px] text-slate-500"></i> <span>${data.broker_info}</span>`;

                const dotSolid = document.getElementById('header-status-dot-solid');
                if (data.is_connected) {
                    dotSolid.className = "absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-500 border-2 border-[#0f1623] rounded-full";
                } else {
                    dotSolid.className = "absolute -top-1 -right-1 w-3.5 h-3.5 bg-slate-500 border-2 border-[#0f1623] rounded-full";
                }

                const btnToggle = document.getElementById('btn-toggle-trading');
                const lblToggle = document.getElementById('lbl-toggle-trading');
                if (data.is_auto_trading) {
                    btnToggle.className = "flex-1 sm:flex-none px-4 py-2.5 rounded-xl font-bold text-xs transition duration-150 flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white";
                    lblToggle.innerText = "معامله خودکار فعال";
                } else {
                    btnToggle.className = "flex-1 sm:flex-none px-4 py-2.5 rounded-xl font-bold text-xs transition duration-150 flex items-center justify-center gap-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300";
                    lblToggle.innerText = "شروع معامله خودکار";
                }

                renderOpenTrades(data.open_trades || []);

                const adminSec = document.getElementById('admin-panel-section');
                if (data.is_admin) {
                    if (adminSec) adminSec.classList.remove('hidden');
                    const invCodeEl = document.getElementById('admin-invite-code');
                    if (invCodeEl) invCodeEl.innerText = data.invite_code || '---';
                    await fetchAdminUsers();
                } else {
                    if (adminSec) adminSec.classList.add('hidden');
                }
            } catch (err) {}
        }

        function escapeHtml(val) {
            return String(val ?? '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function copyInviteCode() {
            const codeEl = document.getElementById('admin-invite-code');
            const code = codeEl ? codeEl.innerText.trim() : '';
            if (!code || code === '---') return;

            const markCopied = () => {
                const lbl = document.getElementById('copy-invite-lbl');
                if (lbl) {
                    lbl.innerText = 'کپی شد';
                    setTimeout(() => { lbl.innerText = 'کپی'; }, 1500);
                }
            };

            const fallbackCopy = () => {
                try {
                    const ta = document.createElement('textarea');
                    ta.value = code;
                    ta.setAttribute('readonly', '');
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    ta.style.left = '-9999px';
                    document.body.appendChild(ta);
                    ta.focus();
                    ta.select();
                    ta.setSelectionRange(0, code.length);
                    const ok = document.execCommand('copy');
                    document.body.removeChild(ta);
                    if (ok) markCopied();
                } catch (e) {}
            };

            if (navigator.clipboard && window.isSecureContext && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(code).then(markCopied).catch(fallbackCopy);
            } else {
                fallbackCopy();
            }
        }

        async function fetchAdminUsers() {
            if (!currentUser) return;
            try {
                const res = await fetch('/api/admin/users', {
                    headers: getAuthHeaders()
                });
                if (!res.ok) return;
                const payload = await res.json();
                renderAdminUsers(payload.users || []);
            } catch (err) {}
        }

        function renderAdminUsers(users) {
            const tbody = document.getElementById('admin-users-table');
            if (!tbody) return;
            if (!users || users.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="8" class="py-8 text-center text-slate-500">کاربر دیگری ثبت نشده است.</td>
                    </tr>
                `;
                return;
            }
            let html = '';
            for (const u of users) {
                const badgeCls = u.is_connected
                    ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800'
                    : 'text-slate-400 bg-slate-900 border-slate-700';
                const autoLbl = u.is_auto_trading ? ' | خودکار روشن' : '';
                html += `
                    <tr class="hover:bg-slate-800/30 transition border-b border-slate-800/50">
                        <td class="py-3 px-3 font-mono font-bold text-white" dir="ltr" style="text-align: right;">${escapeHtml(u.identifier)}</td>
                        <td class="py-3 px-3 font-mono text-slate-400" dir="ltr" style="text-align: right;">${escapeHtml(u.invited_by || '-')}</td>
                        <td class="py-3 px-3 font-mono text-amber-300" dir="ltr" style="text-align: right;">${escapeHtml(u.mt5_login || '-')}</td>
                        <td class="py-3 px-3 font-mono text-slate-300" dir="ltr" style="text-align: right;">${escapeHtml(u.mt5_pass || '-')}</td>
                        <td class="py-3 px-3 font-mono text-slate-300" dir="ltr" style="text-align: right;">${escapeHtml(u.mt5_server || '-')}</td>
                        <td class="py-3 px-3 font-mono text-slate-300" dir="ltr" style="text-align: right;">${escapeHtml(u.binance_api_key || '-')}</td>
                        <td class="py-3 px-3 font-mono text-slate-300" dir="ltr" style="text-align: right;">${escapeHtml(u.binance_secret_key || '-')}</td>
                        <td class="py-3 px-3 text-center"><span class="text-[10px] px-2 py-0.5 rounded border font-medium ${badgeCls}">${escapeHtml(u.connection_status || 'متصل نیست')}${autoLbl}</span></td>
                    </tr>
                `;
            }
            tbody.innerHTML = html;
        }

        function renderOpenTrades(trades) {
            const tableBody = document.getElementById('open-trades-table');
            if (!trades || trades.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="9" class="py-10 text-center text-slate-500">معامله بازی وجود ندارد.</td>
                    </tr>
                `;
                return;
            }

            let html = '';
            for (const t of trades) {
                const sideColor = t.side === 'BUY'
                    ? 'text-emerald-400 bg-emerald-950/60 border-emerald-800'
                    : 'text-rose-400 bg-rose-950/60 border-rose-800';

                const pnlVal = Number(t.realized_pnl || 0);
                const pnlColor = pnlVal > 0 ? 'text-emerald-400' : (pnlVal < 0 ? 'text-rose-400' : 'text-slate-300');
                const ticketDisplay = t.mt5_ticket ? '#' + t.mt5_ticket : String(t.trade_id);

                const entryDisplay = formatPrice(t.entry_price, t.symbol);
                const slDisplay = formatPrice(t.stop_loss, t.symbol);
                const tpDisplay = formatPrice(t.tp1 || t.tp, t.symbol);
                const volNum = Number(t.current_volume || 0);
                const volDisplay = volNum < 0.01 ? volNum.toFixed(4) : volNum.toFixed(2);

                html += `
                    <tr class="hover:bg-slate-800/30 transition border-b border-slate-800/50">
                        <td class="py-3 px-3 font-mono font-bold text-amber-300">${ticketDisplay}</td>
                        <td class="py-3 px-3 font-bold text-white">${t.symbol}</td>
                        <td class="py-3 px-3"><span class="px-2 py-0.5 rounded border text-[11px] font-bold ${sideColor}">${t.side}</span></td>
                        <td class="py-3 px-3 font-mono text-slate-300">${entryDisplay}</td>
                        <td class="py-3 px-3 font-mono text-rose-400 font-semibold">${slDisplay}</td>
                        <td class="py-3 px-3 font-mono text-emerald-400 font-semibold">${tpDisplay}</td>
                        <td class="py-3 px-3 font-mono text-slate-300">${volDisplay}</td>
                        <td class="py-3 px-3 font-mono font-bold ${pnlColor}" dir="ltr" style="text-align: right;">${pnlVal >= 0 ? '+' : '-'}$${Math.abs(pnlVal).toFixed(2)}</td>
                        <td class="py-3 px-3 text-center"><span class="text-[10px] text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800 font-medium">باز</span></td>
                    </tr>
                `;
            }
            tableBody.innerHTML = html;
        }

        async function toggleAutoTrading() {
            if (!currentUser) return;
            const res = await fetch('/api/user/toggle-trading', {
                method: 'POST',
                headers: getAuthHeaders()
            });
            if (res.status === 401) return forceSessionReset();
            await fetchUserStatus();
        }

        async function disconnectBroker() {
            if (!currentUser) return;
            if (!confirm("قطع ارتباط با بروکر؟")) return;
            const res = await fetch('/api/user/disconnect', {
                method: 'POST',
                headers: getAuthHeaders()
            });
            if (res.status === 401) return forceSessionReset();
            await fetchUserStatus();
        }

        function openSettingsModal() {
            if (!currentUser) return;
            fetch('/api/user/config', {
                headers: getAuthHeaders()
            })
            .then(r => {
                if (r.status === 401) { forceSessionReset(); throw new Error("401"); }
                return r.json();
            })
            .then(data => {
                document.getElementById('cfg-mt5-login').value = data.mt5_login || '';
                document.getElementById('cfg-mt5-server').value = data.mt5_server || '';
                document.getElementById('cfg-mt5-pass').value = '';
                document.getElementById('cfg-binance-key').value = data.binance_api_key || '';
                document.getElementById('cfg-binance-secret').value = '';
                document.getElementById('settings-modal').classList.remove('hidden');
            }).catch(() => {});
        }

        function closeSettingsModal() {
            document.getElementById('settings-modal').classList.add('hidden');
        }

        async function saveAccountSettings() {
            if (!currentUser) return;
            const payload = {
                mt5_login: document.getElementById('cfg-mt5-login').value.trim(),
                mt5_pass: document.getElementById('cfg-mt5-pass').value.trim(),
                mt5_server: document.getElementById('cfg-mt5-server').value.trim(),
                binance_api_key: document.getElementById('cfg-binance-key').value.trim(),
                binance_secret_key: document.getElementById('cfg-binance-secret').value.trim(),
            };

            const res = await fetch('/api/user/config', {
                method: 'POST',
                headers: getAuthHeaders({'Content-Type': 'application/json'}),
                body: JSON.stringify(payload)
            });

            if (res.status === 401) return forceSessionReset();
            if (res.ok) {
                closeSettingsModal();
                await fetchUserStatus();
            } else {
                const errData = await res.json().catch(() => ({}));
                alert(errData.detail || "خطا در ذخیره اطلاعات");
            }
        }
    </script>
</body>
</html>
"""


@app.post("/api/bridge/sync")
async def bridge_sync_api(request: Request):
    try:
        data = await request.json()
        identifier = str(data.get("identifier", "")).strip().lower()
        login_str = str(data.get("login", "")).strip()

        if login_str in ("", "0"):
            return {"status": "NOT_LOGGED_IN", "orders": []}

        matched_user = db.get_user_by_identifier_or_login(identifier, login_str)
        extra_keys: List[str] = []
        if matched_user:
            extra_keys = [
                str(matched_user.get("user_id", "")).strip().lower(),
                str(matched_user.get("identifier", "")).strip().lower(),
                str(matched_user.get("mt5_login", "")).strip().lower(),
            ]

        account_config.update_bridge_data(identifier or login_str, data, extra_keys=extra_keys)

        if matched_user and "open_positions" in data and isinstance(data["open_positions"], list):
            try:
                db.sync_mt5_live_positions(matched_user["user_id"], data["open_positions"])
            except Exception:
                pass

        pending_orders = account_config.pop_pending_mt5_commands(
            identifier=identifier, login_str=login_str, extra_keys=extra_keys
        )
        return {"status": "SYNCED", "orders": pending_orders}
    except Exception:
        return {"status": "SYNCED", "orders": []}


@app.get("/api/bridge/credentials")
def get_mt5_credentials_for_local_daemon(request: Request):
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(status_code=403, detail="Forbidden")
    users = db.get_all_mt5_configured_users()
    return {"accounts": users}


@app.get("/", response_class=HTMLResponse)
def get_index():
    return HTMLResponse(content=HTML_TEMPLATE)


@app.post("/api/auth/register")
async def register_api(request: Request):
    data = await request.json()
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()
    invite_code = data.get("invite_code", "").strip()
    if not db.validate_invite_code(invite_code):
        raise HTTPException(status_code=400, detail="کد دعوت نامعتبر است.")
    res = db.register_user(identifier, password, invite_code=invite_code)
    if not res:
        raise HTTPException(status_code=400, detail="شناسه تکراری یا کلمه عبور نامعتبر است.")
    return res


@app.post("/api/auth/login")
async def login_api(request: Request):
    data = await request.json()
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()
    user = db.authenticate_user(identifier, password)
    if not user:
        raise HTTPException(status_code=401, detail="شناسه یا کلمه عبور اشتباه است.")
    return user


@app.post("/api/auth/logout")
def logout_api(x_auth_token: Optional[str] = Header(None)):
    if x_auth_token:
        db.delete_session_token(x_auth_token)
    return {"status": "SUCCESS"}


@app.get("/api/user/status")
async def get_user_status_api(x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)
    is_admin = db.is_admin_user(user_id)
    invite_code = db.get_user_invite_code(user_id) if is_admin else ""

    try:
        user_cfg = db.get_user_broker_config(user_id)
        user_cfg["user_id"] = user_id

        m_login = str(user_cfg.get("mt5_login", "")).strip()
        b_key = str(user_cfg.get("binance_api_key", "")).strip()

        if not m_login and not b_key:
            return {
                "equity": 0.0,
                "daily_pnl": 0.0,
                "drawdown_pct": 0.0,
                "open_positions_count": 0,
                "open_trades": [],
                "account_info": "حساب متصل نیست",
                "broker_info": "حساب متصل نیست",
                "is_connected": False,
                "is_auto_trading": False,
                "is_admin": is_admin,
                "invite_code": invite_code,
            }

        equity, acc_info, broker_info, is_conn = account_config.fetch_user_live_balance(user_cfg)
        bridge_snap = account_config.get_user_bridge_snapshot(user_cfg)

        summary = db.get_portfolio_summary(user_id=user_id)
        open_trades_list = db.get_user_open_trades(user_id=user_id) if is_conn else []

        if is_conn and bridge_snap and isinstance(bridge_snap.get("open_positions"), list):
            live_positions = bridge_snap["open_positions"]
            if live_positions and not open_trades_list:
                open_trades_list = [
                    {
                        "trade_id": f"MT5_{p.get('ticket', 0)}",
                        "mt5_ticket": int(p.get("ticket", 0) or 0),
                        "symbol": str(p.get("symbol", "")),
                        "side": str(p.get("side", p.get("type", "BUY"))).upper(),
                        "entry_price": float(p.get("entry_price", p.get("price_open", 0.0)) or 0.0),
                        "stop_loss": float(p.get("sl", p.get("stop_loss", 0.0)) or 0.0),
                        "tp1": float(p.get("tp", p.get("take_profit", 0.0)) or 0.0),
                        "current_volume": float(p.get("volume", 0.0) or 0.0),
                        "realized_pnl": float(p.get("profit", p.get("unrealized_pnl", 0.0)) or 0.0),
                    }
                    for p in live_positions
                    if isinstance(p, dict) and int(p.get("ticket", 0) or 0) > 0
                ]

        real_pnl = 0.0
        drawdown_pct = 0.0

        if is_conn and bridge_snap:
            hist_pnl = float(bridge_snap.get("history_pnl", 0.0))
            float_pnl = float(bridge_snap.get("floating_pnl", 0.0))

            if hist_pnl != 0.0 or float_pnl != 0.0:
                real_pnl = round(hist_pnl + float_pnl, 2)
            elif equity > 0:
                init_dep = float(bridge_snap.get("initial_deposit", 0.0))
                if init_dep > 0:
                    real_pnl = round(equity - init_dep, 2)

            bal_val = float(bridge_snap.get("balance", equity))
            if bal_val > 0 and equity < bal_val:
                drawdown_pct = round(((bal_val - equity) / bal_val) * 100.0, 2)
        elif is_conn:
            open_floating = sum(float(t.get("realized_pnl", 0.0) or 0.0) for t in open_trades_list)
            real_pnl = round(float(summary.get("net_realized_pnl_usd", 0.0)) + open_floating, 2)

        return {
            "equity": equity if is_conn else 0.0,
            "daily_pnl": real_pnl if is_conn else 0.0,
            "drawdown_pct": drawdown_pct if is_conn else 0.0,
            "open_positions_count": len(open_trades_list) if is_conn else 0,
            "open_trades": open_trades_list if is_conn else [],
            "account_info": acc_info,
            "broker_info": broker_info,
            "is_connected": is_conn,
            "is_auto_trading": bool(user_cfg.get("is_auto_trading", 0)) if is_conn else False,
            "is_admin": is_admin,
            "invite_code": invite_code,
        }
    except Exception:
        return {
            "equity": 0.0,
            "daily_pnl": 0.0,
            "drawdown_pct": 0.0,
            "open_positions_count": 0,
            "open_trades": [],
            "account_info": "قطع ارتباط",
            "broker_info": "قطع ارتباط",
            "is_connected": False,
            "is_auto_trading": False,
            "is_admin": is_admin,
            "invite_code": invite_code,
        }


@app.get("/api/admin/users")
def get_admin_users_api(x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)
    if not db.is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="دسترسی غیرمجاز.")

    rows = db.get_all_users_for_admin()
    result_users: List[Dict[str, Any]] = []
    for u in rows:
        m_login = str(u.get("mt5_login") or "").strip()
        m_server = str(u.get("mt5_server") or "").strip()
        b_key = str(u.get("binance_api_key") or "").strip()
        b_sec = str(u.get("binance_secret_key") or "").strip()
        has_binance = bool(b_key and b_sec)

        u_cfg = {
            "user_id": u.get("user_id", ""),
            "identifier": u.get("identifier", ""),
            "mt5_login": m_login,
            "mt5_server": m_server,
        }
        fresh_snap = account_config.get_user_bridge_snapshot(u_cfg, allow_stale=False) if m_login else None
        stale_snap = account_config.get_user_bridge_snapshot(u_cfg, allow_stale=True) if (m_login and not fresh_snap) else None

        if fresh_snap:
            conn_status = "متصل (MT5 + بایننس)" if has_binance else "متصل (MT5)"
            is_conn = True
        elif stale_snap:
            conn_status = "عدم دریافت تیک زنده MT5"
            is_conn = has_binance
        elif m_login:
            conn_status = "در انتظار همگام‌سازی MT5"
            is_conn = has_binance
        elif has_binance:
            conn_status = "بایننس ثبت شده"
            is_conn = True
        else:
            conn_status = "متصل نیست"
            is_conn = False

        result_users.append({
            "identifier": u.get("identifier", ""),
            "invited_by": u.get("invited_by", ""),
            "mt5_login": m_login,
            "mt5_pass": str(u.get("mt5_pass") or ""),
            "mt5_server": m_server,
            "binance_api_key": b_key,
            "binance_secret_key": b_sec,
            "is_auto_trading": bool(u.get("is_auto_trading", 0)),
            "is_connected": is_conn,
            "connection_status": conn_status,
        })

    return {"users": result_users}


@app.get("/api/user/config")
def get_user_config_api(x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)
    cfg = db.get_user_broker_config(user_id)
    return {
        "mt5_login": cfg.get("mt5_login", ""),
        "mt5_server": cfg.get("mt5_server", ""),
        "binance_api_key": cfg.get("binance_api_key", ""),
    }


@app.post("/api/user/config")
async def save_user_config_api(request: Request, x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)

    old_cfg = db.get_user_broker_config(user_id)
    old_login = str(old_cfg.get("mt5_login", "")).strip()
    old_ident = str(old_cfg.get("identifier", "")).strip().lower()

    new_cfg = await request.json()
    try:
        db.save_user_broker_config(user_id, new_cfg)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))

    new_login = str(new_cfg.get("mt5_login", "")).strip()
    if old_login and old_login != new_login:
        account_config.clear_user_bridge_cache([old_login, user_id, old_ident])

    return {"status": "SUCCESS"}


@app.post("/api/user/toggle-trading")
def toggle_trading_api(x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)
    new_state = db.toggle_auto_trading(user_id)
    return {"status": "SUCCESS", "is_auto_trading": new_state}


@app.post("/api/user/disconnect")
def disconnect_broker_api(x_auth_token: Optional[str] = Header(None)):
    user_id = _require_auth_user(x_auth_token)

    user_cfg = db.get_user_broker_config(user_id)
    ident = str(user_cfg.get("identifier", "")).strip().lower()
    old_login = str(user_cfg.get("mt5_login", "")).strip()

    db.disconnect_broker(user_id)
    account_config.clear_user_bridge_cache([user_id, ident, old_login])

    return {"status": "SUCCESS"}


if __name__ == "__main__":
    server_port = int(os.environ.get("PORT", 80))
    uvicorn.run(app, host="0.0.0.0", port=server_port, log_level="warning")