"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 12: MULTI-TENANT AUTOMATIC MT5 INSTANCE MANAGER (ares_mt5_manager.py)
VERSION: 14.6 (VIRTUAL WINE DESKTOP, UNIVERSAL BROKER SUPPORT & EXACT PID TRACKING)
================================================================================
"""

import os
import sys
import time
import shutil
import subprocess
from typing import Dict, List, Any, Optional
from ares_database import AresDatabaseManager

INSTANCES_DIR = "/root/mt5_instances"
BASE_MT5_DIR = "/root/.wine/drive_c/Program Files/MetaTrader 5"
GLOBAL_CONFIG_SRC = "/root/mt5_config"

# جدول نگاشت هوشمند نام استاندارد بروکرهای جهانی
UNIVERSAL_BROKER_MAP = {
    "metaquotes-demo": "MetaQuotes-Demo",
    "metaquotes": "MetaQuotes-Demo",
    "aronmarkets-demo": "AronMarkets-Demo",
    "aronmarkets-live": "AronMarkets-Live",
}


class AresMT5MultiManager:
    """
    ناظر خودکار متاتریدر ۵ با پشتیبانی از تمامی بروکرهای معتبر جهان،
    دسکتاپ مجازی ایزوله Wine و جلوگیری از اجرای پروسه‌های تکراری.
    """

    def __init__(self, db: Optional[AresDatabaseManager] = None):
        self.db = db or AresDatabaseManager()
        os.makedirs(INSTANCES_DIR, exist_ok=True)

    def get_configured_accounts(self) -> List[Dict[str, Any]]:
        """دریافت تمام حساب‌های متاتریدر ثبت‌شده توسط کاربران از دیتابیس"""
        try:
            return self.db.get_all_mt5_configured_users()
        except Exception as e:
            print(f"⚠️ [خطای دیتابیس در خواندن حساب‌ها]: {e}", flush=True)
            return []

    def is_login_running(self, login: str) -> bool:
        """بررسی دقیق روشن بودن متاتریدر کاربر بدون اجازه به اجرای تکراری"""
        clean_login = str(login).strip()
        if not clean_login:
            return False

        user_dir = os.path.realpath(os.path.join(INSTANCES_DIR, clean_login))
        pid_file = os.path.join(user_dir, "mt5.pid")

        # ۱. بررسی از روی نام دسکتاپ مجازی Wine اختصاصی کاربر
        try:
            res = subprocess.run(["pgrep", "-f", f"MT5_{clean_login}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and res.stdout.strip():
                return True
        except Exception:
            pass

        # ۲. بررسی دقیق مسیر کاری (cwd) پروسه‌های فعال terminal64.exe
        try:
            res_t = subprocess.run(["pgrep", "-f", "terminal64.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res_t.returncode == 0 and res_t.stdout.strip():
                for pid_bytes in res_t.stdout.strip().splitlines():
                    pid_str = pid_bytes.decode(errors="ignore").strip()
                    if not pid_str:
                        continue
                    try:
                        cwd = os.path.realpath(f"/proc/{pid_str}/cwd")
                        if cwd == user_dir:
                            return True
                    except Exception:
                        pass
        except Exception:
            pass

        # ۳. بررسی فایل PID اختصاصی کاربر
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return True
            except (OSError, ValueError):
                try:
                    os.remove(pid_file)
                except Exception:
                    pass

        return False

    def setup_user_environment(self, user: Dict[str, Any]) -> Optional[str]:
        """آماده‌سازی خودکار پوشه ایزوله و فایل کانفیگ برای هر بروکر در دنیا"""
        login = str(user.get("mt5_login", "")).strip()
        password = str(user.get("mt5_pass", "")).strip()
        server_raw = str(user.get("mt5_server", "MetaQuotes-Demo")).strip() or "MetaQuotes-Demo"

        if not login or not password:
            return None

        # تبدیل هوشمند نام بروکر به نام رسمی داخل servers.dat
        server_lower = server_raw.lower()
        server_endpoint = UNIVERSAL_BROKER_MAP.get(server_lower, server_raw)

        user_dir = os.path.join(INSTANCES_DIR, login)
        config_dir = os.path.join(user_dir, "config")
        experts_dir = os.path.join(user_dir, "MQL5", "Experts")

        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(experts_dir, exist_ok=True)

        # ۱. پیوند فایل‌های اجرایی متاتریدر به پوشه اختصاصی کاربر
        if os.path.exists(BASE_MT5_DIR):
            for fname in os.listdir(BASE_MT5_DIR):
                src = os.path.join(BASE_MT5_DIR, fname)
                dst = os.path.join(user_dir, fname)
                if os.path.isfile(src) and (fname.lower().endswith(".exe") or fname.lower().endswith(".dll")):
                    if not os.path.exists(dst):
                        try:
                            os.link(src, dst)
                        except Exception:
                            try:
                                shutil.copy2(src, dst)
                            except Exception:
                                pass

            for folder in ["profiles", "templates", "help", "sounds"]:
                src_f = os.path.join(BASE_MT5_DIR, folder)
                dst_f = os.path.join(user_dir, folder)
                if os.path.exists(src_f) and not os.path.exists(dst_f):
                    try:
                        os.symlink(src_f, dst_f)
                    except Exception:
                        pass

            base_mql5 = os.path.join(BASE_MT5_DIR, "MQL5")
            if os.path.exists(base_mql5):
                for sub in ["Include", "Indicators", "Libraries", "Scripts", "Images"]:
                    src_sub = os.path.join(base_mql5, sub)
                    dst_sub = os.path.join(user_dir, "MQL5", sub)
                    if os.path.exists(src_sub) and not os.path.exists(dst_sub):
                        try:
                            os.symlink(src_sub, dst_sub)
                        except Exception:
                            pass

        # ۲. قرار دادن اکسپرت رابط AresBridgeEA در پوشه کاربر
        ea_sources = [
            os.path.join(BASE_MT5_DIR, "MQL5", "Experts", "AresBridgeEA.ex5"),
            "/root/ARES_SYSTEM/AresBridgeEA.ex5",
        ]
        target_ea = os.path.join(experts_dir, "AresBridgeEA.ex5")
        for src_ea in ea_sources:
            if os.path.exists(src_ea):
                try:
                    shutil.copy2(src_ea, target_ea)
                    break
                except Exception:
                    pass

        # ۳. انتقال کانفیگ سرورها
        if os.path.exists(GLOBAL_CONFIG_SRC):
            subprocess.run(f"cp -rf '{GLOBAL_CONFIG_SRC}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)
        base_config = os.path.join(BASE_MT5_DIR, "config")
        if os.path.exists(base_config):
            subprocess.run(f"cp -n '{base_config}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)

        # ۴. انتخاب هوشمند نماد استارت متناسب با بروکر
        start_symbol = "EURUSD." if "aron" in server_lower else "EURUSD"

        # ۵. ساخت فایل کانفیگ استارت متاتریدر
        ini_path = os.path.join(user_dir, "mt5_start.ini")
        ini_content = f"""[Common]
Login={login}
Password={password}
Server={server_endpoint}

[Experts]
AllowLiveTrading=1
AllowDllImport=1
Enabled=1
Account=1
Profile=
WebRequest=1
WebRequestUrl=http://141.98.166.81,http://127.0.0.1,http://localhost

[Start]
Expert=AresBridgeEA
Symbol={start_symbol}
Period=M15
"""
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        return user_dir

    def launch_instance(self, user: Dict[str, Any]) -> bool:
        """اجرای متاتریدر اختصاصی داخل دسکتاپ مجازی ایزوله Wine و ثبت PID"""
        login = str(user.get("mt5_login", "")).strip()
        server = str(user.get("mt5_server", "MetaQuotes-Demo")).strip()

        user_dir = self.setup_user_environment(user)
        if not user_dir:
            return False

        pid_file = os.path.join(user_dir, "mt5.pid")
        desktop_name = f"MT5_{login}"
        wine_log = os.path.join(user_dir, "wine_mt5.log")

        # اجرای متاتریدر در دسکتاپ مجازی اختصاصی Wine روی مانیتور :99
        launch_cmd = (
            f"cd '{user_dir}' && "
            f"DISPLAY=:99 nohup wine explorer /desktop={desktop_name},1280x1024 terminal64.exe /portable /config:mt5_start.ini > '{wine_log}' 2>&1 & "
            f"echo $! > '{pid_file}'"
        )

        print(f"🚀 [ARES CLOUD MANAGER]: در حال اجرای متاتریدر اکانت {login} ({server}) روی دسکتاپ {desktop_name}...", flush=True)
        try:
            subprocess.run(launch_cmd, shell=True, check=False)
            dismiss_cmd = "(sleep 4 && DISPLAY=:99 xdotool key Escape Return 2>/dev/null) &"
            subprocess.run(dismiss_cmd, shell=True, check=False)
            return True
        except Exception as e:
            print(f"⚠️ [خطا در اتصال اکانت {login}]: {e}", flush=True)
            return False

    def sync_all_user_instances(self):
        """رصد دائم و روشن کردن متاتریدر هر کاربری که در سایت اطلاعات وارد کرده"""
        accounts = self.get_configured_accounts()
        for user in accounts:
            login = str(user.get("mt5_login", "")).strip()
            if login and not self.is_login_running(login):
                self.launch_instance(user)
                time.sleep(3)

    def run_supervisor(self, poll_interval_seconds: int = 10):
        print("=" * 80, flush=True)
        print("🌟 ناظر هوشمند ابری متاتریدرها (ARES V14.6 - دسکتاپ مجازی Wine و اتصال جهانی) فعال شد.", flush=True)
        print("=" * 80, flush=True)

        while True:
            try:
                self.sync_all_user_instances()
            except Exception as e:
                print(f"⚠️ [خطای ناظر ابری]: {e}", flush=True)
            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    manager = AresMT5MultiManager()
    manager.run_supervisor()