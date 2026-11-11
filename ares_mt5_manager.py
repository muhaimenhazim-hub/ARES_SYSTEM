"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 12: MULTI-TENANT AUTOMATIC MT5 INSTANCE MANAGER (ares_mt5_manager.py)
VERSION: 14.3 (TRUE ISOLATED PORTABLE RUNTIMES PER USER)
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


class AresMT5MultiManager:
    """
    ناظر و مدیر خودکار متاتریدر ۵ برای تمام کاربران سامانه ARES.
    هر کاربری که مشخصات لاگین متاتریدر را در سایت وارد کند،
    این ماژول به صورت ۱۰۰٪ خودکار یک متاتریدر کاملاً ایزوله برای او در سرور بالا می‌آورد.
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
        """بررسی دقیق فعال بودن متاتریدر اختصاصی این کاربر در سرور بدون باگ جستجوی شل"""
        clean_login = str(login).strip()
        if not clean_login:
            return False
        try:
            # اجرای مستقیم pgrep بدون shell=True تا پروسه جستجو خودش را پیدا نکند
            res1 = subprocess.run(["pgrep", "-f", f"mt5_{clean_login}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res1.returncode == 0:
                return True
            res2 = subprocess.run(["pgrep", "-f", f"mt5_instances/{clean_login}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res2.returncode == 0:
                return True
            # سازگاری با اکانت قدیمی 300260 که تحت دسکتاپ MT5 در حال اجراست
            if clean_login == "300260":
                res3 = subprocess.run(["pgrep", "-f", "desktop=MT5"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res3.returncode == 0:
                    return True
            return False
        except Exception:
            return False

    def setup_user_environment(self, user: Dict[str, Any]) -> Optional[str]:
        """آماده‌سازی خودکار پوشه و فایل‌های اجرایی اختصاصی و ایزوله برای این کاربر"""
        login = str(user.get("mt5_login", "")).strip()
        password = str(user.get("mt5_pass", "")).strip()
        server = str(user.get("mt5_server", "MetaQuotes-Demo")).strip() or "MetaQuotes-Demo"

        if not login or not password:
            return None

        user_dir = os.path.join(INSTANCES_DIR, login)
        config_dir = os.path.join(user_dir, "config")
        experts_dir = os.path.join(user_dir, "MQL5", "Experts")

        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(experts_dir, exist_ok=True)

        # ۱. لینک/کپی فایل‌های اجرایی اصلی متاتریدر به پوشه اختصاصی کاربر
        if os.path.exists(BASE_MT5_DIR):
            for fname in os.listdir(BASE_MT5_DIR):
                src = os.path.join(BASE_MT5_DIR, fname)
                dst = os.path.join(user_dir, fname)
                if os.path.isfile(src) and (fname.lower().endswith(".exe") or fname.lower().endswith(".dll")):
                    if not os.path.exists(dst):
                        try:
                            os.link(src, dst)  # هاردلینک مستقیم (بدون مصرف حجم هارد)
                        except Exception:
                            try:
                                shutil.copy2(src, dst)
                            except Exception:
                                pass

            # پوشه‌های تکمیلی مورد نیاز متاتریدر
            for folder in ["profiles", "templates", "help", "sounds"]:
                src_f = os.path.join(BASE_MT5_DIR, folder)
                dst_f = os.path.join(user_dir, folder)
                if os.path.exists(src_f) and not os.path.exists(dst_f):
                    try:
                        os.symlink(src_f, dst_f)
                    except Exception:
                        pass

            # پوشه‌های MQL5 به جز Experts
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

        # ۲. کپی فایل اکسپرت کامپایل‌شده ARES Bridge
        base_ea = os.path.join(BASE_MT5_DIR, "MQL5", "Experts", "AresBridgeEA.ex5")
        target_ea = os.path.join(experts_dir, "AresBridgeEA.ex5")
        if os.path.exists(base_ea):
            try:
                shutil.copy2(base_ea, target_ea)
            except Exception:
                pass

        # ۳. کپی فایل‌های سرور بروکرها (servers.dat)
        if os.path.exists(GLOBAL_CONFIG_SRC):
            subprocess.run(f"cp -rf '{GLOBAL_CONFIG_SRC}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)
        base_config = os.path.join(BASE_MT5_DIR, "config")
        if os.path.exists(base_config):
            subprocess.run(f"cp -rf '{base_config}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)

        # ۴. ساخت خودکار فایل تنظیمات اختصاصی لاگین متاتریدر
        ini_path = os.path.join(user_dir, "mt5_start.ini")
        ini_content = f"""[Common]
Login={login}
Password={password}
Server={server}

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
Symbol=EURUSD
Period=M15
"""
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        return user_dir

    def launch_instance(self, user: Dict[str, Any]) -> bool:
        """اجرای خودکار متاتریدر ایزوله از داخل پوشه اختصاصی کاربر"""
        login = str(user.get("mt5_login", "")).strip()
        server = str(user.get("mt5_server", "MetaQuotes-Demo")).strip()

        user_dir = self.setup_user_environment(user)
        if not user_dir:
            return False

        user_terminal = os.path.join(user_dir, "terminal64.exe")
        if not os.path.exists(user_terminal):
            user_terminal = os.path.join(BASE_MT5_DIR, "terminal64.exe")

        ini_path = os.path.join(user_dir, "mt5_start.ini")

        # اجرای متاتریدر مستقیم از داخل پوشه خودِ کاربر در حالت پرتابل واقعی
        launch_cmd = (
            f"cd '{user_dir}' && "
            f"DISPLAY=:99 wine explorer /desktop=mt5_{login},1024x768 "
            f"'{user_terminal}' /portable /config:'{ini_path}' > /dev/null 2>&1 &"
        )

        print(f"🚀 [ARES CLOUD MANAGER]: در حال اتصال خودکار متاتریدر اکانت {login} ({server})...", flush=True)
        try:
            subprocess.run(launch_cmd, shell=True, check=False)
            dismiss_cmd = "(sleep 8 && DISPLAY=:99 xdotool key Escape Return 2>/dev/null) &"
            subprocess.run(dismiss_cmd, shell=True, check=False)
            return True
        except Exception as e:
            print(f"⚠️ [خطا در اتصال اکانت {login}]: {e}", flush=True)
            return False

    def sync_all_user_instances(self):
        """رصد منظم دیتابیس و روشن کردن متاتریدر اکانت‌های جدید"""
        accounts = self.get_configured_accounts()
        for user in accounts:
            login = str(user.get("mt5_login", "")).strip()
            if login and not self.is_login_running(login):
                self.launch_instance(user)
                time.sleep(3)

    def run_supervisor(self, poll_interval_seconds: int = 10):
        """حلقه نظارتی دائمی ۲۴ ساعته"""
        print("=" * 80, flush=True)
        print("🌟 ناظر هوشمند ابری متاتریدرها (ARES Multi-Tenant Cloud Manager V14.3) فعال شد.", flush=True)
        print("   هر کاربری در سایت ثبت‌نام کند، متاتریدر او خودکار روی سرور لود خواهد شد.", flush=True)
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