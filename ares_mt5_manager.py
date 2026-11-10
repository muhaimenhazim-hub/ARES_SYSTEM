"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 12: MULTI-TENANT AUTOMATIC MT5 INSTANCE MANAGER (ares_mt5_manager.py)
VERSION: 14.2 (HEADLESS AUTO-LAUNCH, ZERO-CONFIG CLIENT EXPERIENCE)
================================================================================
"""

import os
import sys
import time
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
    این ماژول به صورت ۱۰۰٪ خودکار یک متاتریدر برای او در سرور بالا می‌آورد.
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
        """بررسی فعال بودن متاتریدر اختصاصی این کاربر در سرور"""
        clean_login = str(login).strip()
        if not clean_login:
            return False
        try:
            cmd = f"pgrep -f 'mt5_{clean_login}'"
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode == 0
        except Exception:
            return False

    def setup_user_environment(self, user: Dict[str, Any]) -> Optional[str]:
        """آماده‌سازی خودکار پوشه و فایل‌های اکسپرت و کانفیگ برای این کاربر"""
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

        # ۱. کپی فایل اکسپرت کامپایل‌شده ARES
        base_ea = os.path.join(BASE_MT5_DIR, "MQL5", "Experts", "AresBridgeEA.ex5")
        target_ea = os.path.join(experts_dir, "AresBridgeEA.ex5")
        if os.path.exists(base_ea):
            try:
                subprocess.run(f"cp -f '{base_ea}' '{target_ea}'", shell=True, check=False)
            except Exception:
                pass

        # ۲. کپی فایل‌های سرور بروکرها (servers.dat)
        if os.path.exists(GLOBAL_CONFIG_SRC):
            try:
                subprocess.run(f"cp -rf '{GLOBAL_CONFIG_SRC}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)
            except Exception:
                pass

        base_config = os.path.join(BASE_MT5_DIR, "config")
        if os.path.exists(base_config):
            try:
                subprocess.run(f"cp -rf '{base_config}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)
            except Exception:
                pass

        # ۳. ساخت خودکار فایل کانفیگ اختصاصی این کاربر
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
        """اجرای خودکار متاتریدر برای این کاربر در پس‌زمینه سرور"""
        login = str(user.get("mt5_login", "")).strip()
        server = str(user.get("mt5_server", "MetaQuotes-Demo")).strip()

        user_dir = self.setup_user_environment(user)
        if not user_dir:
            return False

        ini_path = os.path.join(user_dir, "mt5_start.ini")
        terminal_exe = os.path.join(BASE_MT5_DIR, "terminal64.exe")

        launch_cmd = (
            f"DISPLAY=:99 wine explorer /desktop=mt5_{login},1024x768 "
            f"'{terminal_exe}' /portable /datapath:'{user_dir}' /config:'{ini_path}' > /dev/null 2>&1 &"
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
        print("🌟 ناظر هوشمند ابری متاتریدرها (ARES Multi-Tenant Cloud Manager) فعال شد.", flush=True)
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