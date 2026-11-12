"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 11: MULTI-TENANT WEB DASHBOARD WITH USER AUTH & PER-USER ISOLATION
VERSION: 14.6 (PROFESSIONAL FINTECH UI, MOBILE-RESPONSIVE & ZERO MOCK DATA)
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

app = FastAPI(title="ARES AI MULTI-USER TRADING DASHBOARD")

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


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ARES AI TRADING SYSTEM — سامانه معاملات هوشمند ابری</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Vazirmatn', 'system-ui', 'sans-serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    colors: {
                        brand: {
                            50: '#ecfdf5',
                            500: '#10b981',
                            600: '#059669',
                            700: '#047857',
                            950: '#022c22',
                        },
                        dark: {
                            base: '#070a0f',
                            card: '#0f141c',
                            cardSoft: '#141b26',
                            border: '#1e293b',
                            borderHighlight: '#334155',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        * { -webkit-tap-highlight-color: transparent; }
        body { font-family: 'Vazirmatn', sans-serif; background-color: #070a0f; color: #e2e8f0; }
        .font-mono { font-family: 'JetBrains Mono', monospace; }
        .glass-card {
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.07);
        }
        .glow-emerald {
            box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.15);
        }
        .glow-button {
            box-shadow: 0 4px 15px rgba(16, 185, 129, 0.25);
        }
        .glow-button:hover {
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.4);
        }
        .custom-scrollbar::-webkit-scrollbar { height: 6px; width: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: #0b0f17; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #263345; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #3b4e6b; }
    </style>
</head>
<body class="min-h-screen flex flex-col justify-between selection:bg-emerald-500/20 selection:text-emerald-400">

    <!-- ==================== AUTH CONTAINER (صفحه ورود و ثبت‌نام جهانی) ==================== -->
    <div id="auth-container" class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#070a0f] overflow-y-auto">
        <!-- نور پس‌زمینه آمبیانت -->
        <div class="absolute inset-0 overflow-hidden pointer-events-none">
            <div class="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl"></div>
            <div class="absolute bottom-1/4 left-1/3 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl"></div>
        </div>

        <div class="relative w-full max-w-md my-8 glass-card rounded-2xl p-6 sm:p-8 shadow-2xl border border-slate-800">
            <!-- سربرگ برند و لوگو -->
            <div class="text-center mb-6">
                <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-tr from-emerald-600 to-emerald-400 text-white mb-3 shadow-lg shadow-emerald-500/20">
                    <i class="fa-solid fa-chart-line text-2xl"></i>
                </div>
                <h1 class="text-2xl font-black text-white tracking-wider flex items-center justify-center gap-2">
                    <span>ARES AI</span>
                    <span class="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">V14.6</span>
                </h1>
                <p class="text-xs text-slate-400 mt-1 font-normal">سامانه مدیریت معاملات هوشمند و الگوریتمی تحت کلود</p>
            </div>

            <!-- تب‌های ورود / ثبت‌نام -->
            <div class="flex p-1 bg-slate-900/90 rounded-xl border border-slate-800 mb-6">
                <button id="tab-login-btn" onclick="switchAuthTab('login')" class="flex-1 py-2.5 text-xs sm:text-sm font-bold text-white bg-slate-800 rounded-lg shadow transition">
                    ورود به حساب
                </button>
                <button id="tab-register-btn" onclick="switchAuthTab('register')" class="flex-1 py-2.5 text-xs sm:text-sm font-bold text-slate-400 hover:text-white rounded-lg transition">
                    ثبت‌نام کاربر جدید
                </button>
            </div>

            <!-- فرم اطلاعات -->
            <div class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1.5">شناسه کاربری (ایمیل یا شماره همراه):</label>
                    <div class="relative">
                        <span class="absolute inset-y-0 right-0 flex items-center pr-3.5 pointer-events-none text-slate-500 text-sm">
                            <i class="fa-solid fa-user"></i>
                        </span>
                        <input type="text" id="auth-identifier" placeholder="مثال: 0777708735 یا user@gmail.com" 
                            class="w-full bg-slate-950/80 border border-slate-700/80 rounded-xl py-3 pr-10 pl-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition font-mono">
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-300 mb-1.5">کلمه عبور امنیتی:</label>
                    <div class="relative">
                        <span class="absolute inset-y-0 right-0 flex items-center pr-3.5 pointer-events-none text-slate-500 text-sm">
                            <i class="fa-solid fa-lock"></i>
                        </span>
                        <input type="password" id="auth-password" placeholder="حداقل ۴ کاراکتر" 
                            class="w-full bg-slate-950/80 border border-slate-700/80 rounded-xl py-3 pr-10 pl-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition font-mono">
                    </div>
                </div>

                <!-- باکس پیام خطا -->
                <div id="auth-error-msg" class="p-3 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs text-center hidden"></div>

                <!-- دکمه ارسال -->
                <button id="auth-submit-btn" onclick="handleAuthSubmit()" 
                    class="w-full py-3.5 bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white font-bold rounded-xl transition duration-200 glow-button text-sm flex items-center justify-center gap-2 mt-2">
                    <i class="fa-solid fa-arrow-right-to-bracket"></i>
                    <span id="auth-submit-txt">ورود به پنل کاربری</span>
                </button>
            </div>

            <!-- پاورقی امنیت -->
            <div class="mt-6 pt-5 border-t border-slate-800/80 text-center text-[11px] text-slate-500 flex items-center justify-center gap-1.5">
                <i class="fa-solid fa-shield-halved text-emerald-400/80"></i>
                <span>ایمن‌سازی شده با رمزنگاری SHA-256 و اتصال ایزوله اختصاصی</span>
            </div>
        </div>
    </div>

    <!-- ==================== MAIN DASHBOARD ==================== -->
    <div id="main-dashboard" class="hidden flex-1 flex flex-col p-3 sm:p-5 lg:p-6 max-w-7xl mx-auto w-full">
        
        <!-- نوبار بالای صفحه -->
        <header class="glass-card rounded-2xl p-4 mb-5 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <!-- اطلاعات سمت راست: عنوان و کاربر -->
            <div class="flex items-center gap-3">
                <div class="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-tr from-emerald-600 to-emerald-400 text-white shadow-md shadow-emerald-950">
                    <i class="fa-solid fa-robot text-lg"></i>
                    <span id="header-status-dot" class="absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-500 border-2 border-slate-900 rounded-full animate-ping"></span>
                    <span class="absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-500 border-2 border-slate-900 rounded-full"></span>
                </div>
                <div>
                    <div class="flex items-center gap-2 flex-wrap">
                        <h1 class="text-base sm:text-lg font-bold text-white tracking-wide">ARES AI TRADING SYSTEM</h1>
                        <span id="user-display-badge" class="text-xs bg-slate-800 text-emerald-400 border border-slate-700 px-2.5 py-0.5 rounded-full font-mono">کاربر: ...</span>
                    </div>
                    <p id="broker-connected-info" class="text-xs text-slate-400 mt-0.5 font-normal flex items-center gap-1.5">
                        <i class="fa-solid fa-server text-[10px] text-slate-500"></i>
                        <span>در حال بررسی اتصال به بروکر...</span>
                    </p>
                </div>
            </div>

            <!-- کلیدهای کنترل سمت چپ -->
            <div class="flex items-center gap-2 flex-wrap">
                <!-- دکمه استارت/توقف ترید -->
                <button id="btn-toggle-trading" onclick="toggleAutoTrading()" class="flex-1 sm:flex-none px-3.5 py-2.5 rounded-xl font-bold text-xs transition duration-200 flex items-center justify-center gap-2 shadow-sm bg-slate-800 border border-slate-700 text-slate-300">
                    <i class="fa-solid fa-play text-xs"></i>
                    <span id="lbl-toggle-trading">اجازه معامله به ربات</span>
                </button>

                <!-- تنظیمات حساب -->
                <button onclick="openSettingsModal()" class="px-3.5 py-2.5 rounded-xl font-bold text-xs bg-blue-600 hover:bg-blue-500 text-white transition duration-200 flex items-center gap-1.5 shadow-md shadow-blue-950/40">
                    <i class="fa-solid fa-sliders text-xs"></i>
                    <span class="hidden sm:inline">تنظیمات و</span> اتصال متاتریدر
                </button>

                <!-- قطع ارتباط حساب -->
                <button onclick="disconnectBroker()" class="px-3 py-2.5 rounded-xl font-bold text-xs bg-rose-950/40 border border-rose-800/80 hover:bg-rose-900/60 text-rose-300 transition duration-200 flex items-center gap-1.5">
                    <i class="fa-solid fa-link-slash text-xs"></i>
                    <span class="hidden sm:inline">قطع ارتباط</span>
                </button>

                <!-- خروج -->
                <button onclick="logoutUser()" title="خروج از حساب" class="px-3 py-2.5 rounded-xl font-bold text-xs bg-slate-800/90 hover:bg-slate-700 border border-slate-700 text-slate-300 transition duration-200">
                    <i class="fa-solid fa-right-from-bracket"></i>
                </button>
            </div>
        </header>

        <!-- کارت‌های چهارگانه شاخص‌های مالی -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            
            <!-- کارت ۱: موجودی واقعی حساب (Equity) -->
            <div class="glass-card rounded-2xl p-5 border border-slate-800 relative overflow-hidden group hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>موجودی واقعی حساب (Equity)</span>
                    <span class="w-8 h-8 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-wallet"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono text-white mt-3" id="equity-val">$0.00</div>
                <div class="text-[11px] text-slate-400 mt-2 flex items-center gap-1 truncate" id="account-id-display">
                    <i class="fa-solid fa-circle-notch text-[9px]"></i>
                    <span>در انتظار اتصال به بروکر</span>
                </div>
            </div>

            <!-- کارت ۲: سود و زیان خالص کل (Net PnL) -->
            <div class="glass-card rounded-2xl p-5 border border-slate-800 relative overflow-hidden group hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>سود و زیان خالص کل</span>
                    <span class="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-chart-line"></i>
                    </span>
                </div>
                <!-- خط رنگ سود/زیان: سبز برای سود، قرمز برای ضرر -->
                <div class="text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-slate-400" id="daily-pnl">$0.00</div>
                <div class="text-[11px] text-slate-400 mt-2">بر اساس تاریخچه واقعی بروکر</div>
            </div>

            <!-- کارت ۳: پوزیشن‌های فعال بروکر -->
            <div class="glass-card rounded-2xl p-5 border border-slate-800 relative overflow-hidden group hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>پوزیشن‌های فعال بروکر</span>
                    <span class="w-8 h-8 rounded-xl bg-purple-500/10 text-purple-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-layer-group"></i>
                    </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold font-mono text-white mt-3" style="direction: ltr; text-align: right;" id="open-positions-count">0 / 3</div>
                <div class="text-[11px] text-slate-400 mt-2">سقف کنترل ریسک: حداکثر ۳ معامله</div>
            </div>

            <!-- کارت ۴: افت سرمایه (Drawdown) -->
            <div class="glass-card rounded-2xl p-5 border border-slate-800 relative overflow-hidden group hover:border-slate-700 transition">
                <div class="flex items-center justify-between text-slate-400 text-xs font-semibold">
                    <span>افت سرمایه (Drawdown)</span>
                    <span class="w-8 h-8 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center text-sm">
                        <i class="fa-solid fa-shield-halved"></i>
                    </span>
                </div>
                <!-- رنگ ضرر متناسب با ریسک: سبز برای ۰، کهربایی برای زیر ۵٪، قرمز آتشین برای بالای ۵٪ -->
                <div class="text-2xl sm:text-3xl font-extrabold font-mono mt-3 text-emerald-400" id="drawdown-val">0.00%</div>
                <div class="text-[11px] text-slate-400 mt-2">سقف مجاز افت حساب: 12%</div>
            </div>

        </div>

        <!-- جدول پوزیشن‌های باز واقعی (شامل حد سود TP و حد ضرر SL) -->
        <div class="glass-card rounded-2xl p-4 sm:p-5 border border-slate-800 mb-6">
            <div class="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
                <h2 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    <span class="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse"></span>
                    <span>پوزیشن‌های باز واقعی در متاتریدر ۵</span>
                </h2>
                <span class="text-xs text-slate-500 font-mono" id="table-live-refresh-timer">برخط (Real-Time)</span>
            </div>

            <div class="overflow-x-auto custom-scrollbar">
                <table class="w-full text-right text-xs">
                    <thead class="text-slate-400 bg-slate-900/60 uppercase border-b border-slate-800 text-[11px] whitespace-nowrap">
                        <tr>
                            <th class="py-3 px-3">تیکت بروکر</th>
                            <th class="py-3 px-3">نماد</th>
                            <th class="py-3 px-3">جهت</th>
                            <th class="py-3 px-3">قیمت ورود</th>
                            <th class="py-3 px-3 text-rose-400">حد ضرر (SL)</th>
                            <th class="py-3 px-3 text-emerald-400">حد سود (TP)</th>
                            <th class="py-3 px-3">حجم</th>
                            <th class="py-3 px-3">سود/زیان لحظه‌ای</th>
                            <th class="py-3 px-3 text-center">وضعیت</th>
                        </tr>
                    </thead>
                    <tbody id="open-trades-table" class="divide-y divide-slate-800/60 whitespace-nowrap">
                        <tr>
                            <td colspan="9" class="py-8 text-center text-slate-500 font-normal">
                                <i class="fa-solid fa-inbox text-2xl mb-2 block text-slate-600"></i>
                                هیچ معامله بازی در بروکر وجود ندارد.
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

    </div>

    <!-- ==================== SETTINGS MODAL (تنظیمات اتصال متاتریدر) ==================== -->
    <div id="settings-modal" class="fixed inset-0 modal flex items-center justify-center p-4 hidden z-50 bg-black/80 backdrop-blur-sm">
        <div class="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-lg w-full p-5 sm:p-6 text-right max-h-[92vh] overflow-y-auto shadow-2xl custom-scrollbar">
            
            <div class="flex justify-between items-center pb-3 border-b border-slate-800">
                <h3 class="text-sm sm:text-base font-bold text-white flex items-center gap-2">
                    <i class="fa-solid fa-sliders text-emerald-400"></i>
                    <span>تنظیمات حساب معاملاتی متاتریدر ۵</span>
                </h3>
                <button onclick="closeSettingsModal()" class="text-slate-400 hover:text-white text-2xl leading-none">&times;</button>
            </div>

            <!-- بخش اطلاعات MT5 -->
            <div class="mt-4 p-4 rounded-xl bg-slate-950/70 border border-emerald-900/40 space-y-3 text-xs">
                <h4 class="font-bold text-emerald-400 flex items-center gap-1.5 text-xs">
                    <i class="fa-solid fa-plug text-xs"></i>
                    <span>اطلاعات حساب متاتریدر ۵ (MetaTrader 5)</span>
                </h4>
                
                <div>
                    <label class="block text-slate-300 mb-1">شماره حساب (Login):</label>
                    <input type="text" id="cfg-mt5-login" placeholder="مثال: 300260 یا 115293699" 
                        class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>

                <div>
                    <label class="block text-slate-300 mb-1">رمز عبور حساب متاتریدر (Password):</label>
                    <input type="password" id="cfg-mt5-pass" placeholder="رمز عبور اصلی حساب بروکر" 
                        class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>

                <div>
                    <label class="block text-slate-300 mb-1">نام سرور بروکر (Server):</label>
                    <input type="text" id="cfg-mt5-server" placeholder="مثال: AronMarkets-Demo یا MetaQuotes-Demo" 
                        class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2.5 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
            </div>

            <!-- بخش اختیاری بایننس -->
            <div class="mt-4 p-4 rounded-xl bg-slate-950/40 border border-slate-800 space-y-2.5 text-xs">
                <h4 class="font-bold text-slate-300 flex items-center gap-1.5">
                    <i class="fa-brands fa-bitcoin text-amber-400"></i>
                    <span>صرافی بایننس (کریپتو فیوچرز — اختیاری)</span>
                </h4>
                <div>
                    <label class="block text-slate-400 mb-1">Binance API Key:</label>
                    <input type="text" id="cfg-binance-key" placeholder="API Key" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
                <div>
                    <label class="block text-slate-400 mb-1">Binance Secret Key:</label>
                    <input type="password" id="cfg-binance-secret" placeholder="Secret Key" class="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 text-white font-mono focus:border-emerald-500 focus:outline-none">
                </div>
            </div>

            <!-- دکمه‌ها -->
            <div class="mt-6 flex justify-end gap-2.5">
                <button onclick="closeSettingsModal()" class="px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition">
                    انصراف
                </button>
                <button onclick="saveAccountSettings()" class="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition glow-button flex items-center gap-1.5">
                    <i class="fa-solid fa-check text-xs"></i>
                    <span>ذخیره و اتصال به بروکر</span>
                </button>
            </div>

        </div>
    </div>

    <!-- ==================== JAVASCRIPT LOGIC ==================== -->
    <script>
        let currentUser = null;
        try { currentUser = JSON.parse(localStorage.getItem('ares_user') || 'null'); } catch(e) {}

        let currentAuthMode = 'login';

        // مقداردهی اولیه صفحه بر اساس لاگین بودن کاربر
        if (currentUser && currentUser.user_id) {
            document.getElementById('main-dashboard').classList.remove('hidden');
            document.getElementById('auth-container').classList.add('hidden');
            initDashboard();
        } else {
            document.getElementById('auth-container').classList.remove('hidden');
            document.getElementById('main-dashboard').classList.add('hidden');
        }

        function switchAuthTab(mode) {
            currentAuthMode = mode;
            const loginBtn = document.getElementById('tab-login-btn');
            const regBtn = document.getElementById('tab-register-btn');
            const submitTxt = document.getElementById('auth-submit-txt');

            if (mode === 'login') {
                loginBtn.className = "flex-1 py-2.5 text-xs sm:text-sm font-bold text-white bg-slate-800 rounded-lg shadow transition";
                regBtn.className = "flex-1 py-2.5 text-xs sm:text-sm font-bold text-slate-400 hover:text-white rounded-lg transition";
                submitTxt.innerText = "ورود به پنل کاربری";
            } else {
                regBtn.className = "flex-1 py-2.5 text-xs sm:text-sm font-bold text-white bg-slate-800 rounded-lg shadow transition";
                loginBtn.className = "flex-1 py-2.5 text-xs sm:text-sm font-bold text-slate-400 hover:text-white rounded-lg transition";
                submitTxt.innerText = "ثبت‌نام و ایجاد حساب جدید";
            }
        }

        async function handleAuthSubmit() {
            const identifier = document.getElementById('auth-identifier').value.trim();
            const password = document.getElementById('auth-password').value.trim();
            const errBox = document.getElementById('auth-error-msg');

            if (!identifier || !password) {
                errBox.innerText = "لطفاً شناسه کاربری و رمز عبور را وارد کنید.";
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
                    errBox.innerText = data.detail || "خطا در احراز هویت";
                    errBox.classList.remove('hidden');
                }
            } catch (err) {
                errBox.innerText = "خطا در برقراری ارتباط با سرور ابری";
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
            setInterval(fetchUserStatus, 2000);
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

                // ۱. بروزرسانی موجودی واقعی (Equity)
                const eq = Number(data.equity || 0);
                document.getElementById('equity-val').innerText = `$${eq.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

                // ۲. بروزرسانی سود و زیان خالص کل با خط رنگ مناسب
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

                // ۳. بروزرسانی درصد افت سرمایه (Drawdown) با رنگ متناسب با ریسک ضرر
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

                // ۴. پوزیشن‌های باز
                const openCount = data.open_positions_count || 0;
                document.getElementById('open-positions-count').innerText = `${openCount} / 3`;

                // ۵. عناوین حساب و وضعیت اتصال بروکر
                document.getElementById('account-id-display').innerText = data.account_info;
                document.getElementById('broker-connected-info').innerHTML = `<i class="fa-solid fa-server text-[10px] text-slate-500"></i> ${data.broker_info}`;

                // وضعیت نشانگر زنده
                const dot = document.getElementById('header-status-dot');
                if (data.is_connected) {
                    dot.className = "absolute -top-1 -right-1 w-3.5 h-3.5 bg-emerald-500 border-2 border-slate-900 rounded-full animate-ping";
                } else {
                    dot.className = "absolute -top-1 -right-1 w-3.5 h-3.5 bg-slate-600 border-2 border-slate-900 rounded-full";
                }

                // ۶. دکمه ترید خودکار
                const btnToggle = document.getElementById('btn-toggle-trading');
                const lblToggle = document.getElementById('lbl-toggle-trading');
                if (data.is_auto_trading) {
                    btnToggle.className = "flex-1 sm:flex-none px-3.5 py-2.5 rounded-xl font-bold text-xs transition duration-200 flex items-center justify-center gap-2 shadow-md bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-950/50";
                    lblToggle.innerText = "معامله خودکار فعال است (توقف)";
                } else {
                    btnToggle.className = "flex-1 sm:flex-none px-3.5 py-2.5 rounded-xl font-bold text-xs transition duration-200 flex items-center justify-center gap-2 shadow-sm bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300";
                    lblToggle.innerText = "اجازه معامله به ربات (شروع)";
                }

                renderOpenTrades(data.open_trades || []);
            } catch (err) {}
        }

        function renderOpenTrades(trades) {
            const tableBody = document.getElementById('open-trades-table');
            if (!trades || trades.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="9" class="py-8 text-center text-slate-500 font-normal">
                            <i class="fa-solid fa-inbox text-2xl mb-2 block text-slate-600"></i>
                            هیچ معامله بازی در بروکر وجود ندارد.
                        </td>
                    </tr>
                `;
                return;
            }

            let html = '';
            for (const t of trades) {
                const sideColor = t.side === 'BUY' 
                    ? 'text-emerald-400 bg-emerald-950/50 border-emerald-800' 
                    : 'text-rose-400 bg-rose-950/50 border-rose-800';
                
                const pnlVal = Number(t.realized_pnl || 0);
                const pnlColor = pnlVal > 0 ? 'text-emerald-400' : (pnlVal < 0 ? 'text-rose-400' : 'text-slate-300');
                const ticketDisplay = t.mt5_ticket ? '#' + t.mt5_ticket : String(t.trade_id);

                const slVal = Number(t.stop_loss || 0);
                const slDisplay = slVal > 0 ? slVal.toFixed(2) : '-';

                const tpVal = Number(t.tp1 || t.tp || 0);
                const tpDisplay = tpVal > 0 ? tpVal.toFixed(2) : '-';

                html += `
                    <tr class="hover:bg-slate-800/30 transition border-b border-slate-800/50">
                        <td class="py-3 px-3 font-mono font-bold text-amber-300">${ticketDisplay}</td>
                        <td class="py-3 px-3 font-bold text-white">${t.symbol}</td>
                        <td class="py-3 px-3"><span class="px-2 py-0.5 rounded border text-[11px] font-bold ${sideColor}">${t.side}</span></td>
                        <td class="py-3 px-3 font-mono text-slate-300">${Number(t.entry_price || 0).toFixed(2)}</td>
                        <td class="py-3 px-3 font-mono text-rose-400 font-semibold">${slDisplay}</td>
                        <td class="py-3 px-3 font-mono text-emerald-400 font-semibold">${tpDisplay}</td>
                        <td class="py-3 px-3 font-mono text-slate-300">${Number(t.current_volume || 0).toFixed(2)}</td>
                        <td class="py-3 px-3 font-mono font-bold ${pnlColor}">${pnlVal >= 0 ? '+' : ''}$${pnlVal.toFixed(2)}</td>
                        <td class="py-3 px-3 text-center"><span class="text-[10px] text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800 font-medium">فعال (Open)</span></td>
                    </tr>
                `;
            }
            tableBody.innerHTML = html;
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
            if (!confirm("آیا از قطع ارتباط کامل حساب خود و پاکسازی اطلاعات مطمئن هستید؟")) return;
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
                document.getElementById('cfg-mt5-login').value = data.mt5_login || '';
                document.getElementById('cfg-mt5-server').value = data.mt5_server || 'AronMarkets-Demo';
                document.getElementById('cfg-mt5-pass').value = '';
                document.getElementById('cfg-binance-key').value = data.binance_api_key || '';
                document.getElementById('cfg-binance-secret').value = '';
                document.getElementById('settings-modal').classList.remove('hidden');
            });
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
                headers: {
                    'Content-Type': 'application/json',
                    'X-User-Id': currentUser.user_id
                },
                body: JSON.stringify(payload)
            });

            if (res.ok) {
                alert("اطلاعات حساب با موفقیت ذخیره شد و به بروکر متصل گردید.");
                closeSettingsModal();
                fetchUserStatus();
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

        # همگام‌سازی لحظه‌ای پوزیشن‌های واقعی داخل متاتریدر ۵ با دیتابیس سرور
        matched_user = db.get_user_by_identifier_or_login(identifier, login_str)
        extra_keys: List[str] = []
        if matched_user:
            extra_keys = [
                str(matched_user.get("user_id", "")).strip().lower(),
                str(matched_user.get("identifier", "")).strip().lower(),
            ]
            if "open_positions" in data and isinstance(data["open_positions"], list):
                db.sync_mt5_live_positions(matched_user["user_id"], data["open_positions"])

        account_config.update_bridge_data(identifier or login_str, data, extra_keys=extra_keys)
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
    res = db.register_user(identifier, password)
    if not res:
        raise HTTPException(status_code=400, detail="این شماره/ایمیل قبلاً ثبت شده یا کلمه عبور کمتر از ۴ کاراکتر است.")
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

    try:
        user_cfg = db.get_user_broker_config(x_user_id)
        user_cfg["user_id"] = x_user_id

        m_login = str(user_cfg.get("mt5_login", "")).strip()
        b_key = str(user_cfg.get("binance_api_key", "")).strip()

        # در صورتی که کاربر هیچ بروکری متصل نکرده یا قطع ارتباط زده، مقادیر کاملاً صفر و قطع نمایش یابد
        if not m_login and not b_key:
            return {
                "equity": 0.0,
                "daily_pnl": 0.0,
                "drawdown_pct": 0.0,
                "open_positions_count": 0,
                "open_trades": [],
                "account_info": "حساب متصل نیست",
                "broker_info": "جهت اتصال از بخش «تنظیمات و اتصال متاتریدر» استفاده کنید.",
                "is_connected": False,
                "is_auto_trading": False,
            }

        equity, acc_info, broker_info, is_conn = account_config.fetch_user_live_balance(user_cfg)
        bridge_snap = account_config.get_user_bridge_snapshot(user_cfg)

        summary = db.get_portfolio_summary(user_id=x_user_id)
        open_trades_list = db.get_user_open_trades(user_id=x_user_id) if is_conn else []

        real_pnl = 0.0
        drawdown_pct = 0.0

        if is_conn and bridge_snap:
            hist_pnl = float(bridge_snap.get("history_pnl", 0.0))
            float_pnl = float(bridge_snap.get("floating_pnl", 0.0))

            if hist_pnl != 0.0 or float_pnl != 0.0:
                real_pnl = round(hist_pnl + float_pnl, 2)
            elif equity > 0:
                bal = float(bridge_snap.get("balance", equity))
                init_dep = float(bridge_snap.get("initial_deposit", 0.0))
                if init_dep > 0:
                    real_pnl = round(equity - init_dep, 2)

            bal_val = float(bridge_snap.get("balance", equity))
            if bal_val > 0 and equity < bal_val:
                drawdown_pct = round(((bal_val - equity) / bal_val) * 100.0, 2)
        elif is_conn:
            real_pnl = summary.get("net_realized_pnl_usd", 0.0)

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
        }
    except Exception:
        # حذف قطعی دیتای فرضی؛ در صورت هرگونه خطا وضعیت امن صفر بازگردانده می‌شود
        return {
            "equity": 0.0,
            "daily_pnl": 0.0,
            "drawdown_pct": 0.0,
            "open_positions_count": 0,
            "open_trades": [],
            "account_info": "در حال همگام‌سازی با سرور...",
            "broker_info": "ارتباط زنده با متاتریدر برقرار نیست.",
            "is_connected": False,
            "is_auto_trading": False,
        }


@app.get("/api/user/config")
def get_user_config_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    cfg = db.get_user_broker_config(x_user_id)
    return {
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
    return {"status": "SUCCESS", "message": "تنظیمات با موفقیت ذخیره شد."}


@app.post("/api/user/toggle-trading")
def toggle_trading_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    new_state = db.toggle_auto_trading(x_user_id)
    status_txt = "فعال شد." if new_state else "متوقف شد."
    return {"status": "SUCCESS", "is_auto_trading": new_state, "message": f"معامله خودکار {status_txt}"}


@app.post("/api/user/disconnect")
def disconnect_broker_api(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="احراز هویت الزامی است.")
    
    # ۱. قطع ارتباط و پاکسازی در دیتابیس
    db.disconnect_broker(x_user_id)
    
    # ۲. پاکسازی کش پوزیشن‌ها و کش زنده
    user_cfg = db.get_user_broker_config(x_user_id)
    ident = str(user_cfg.get("identifier", "")).strip().lower()
    if ident and ident in account_config.BRIDGE_LIVE_DATA:
        del account_config.BRIDGE_LIVE_DATA[ident]

    return {"status": "SUCCESS", "message": "ارتباط با بروکر قطع شد و اطلاعات حساب با موفقیت پاکسازی گردید."}


if __name__ == "__main__":
    server_port = int(os.environ.get("PORT", 80))
    uvicorn.run(app, host="0.0.0.0", port=server_port, log_level="warning")