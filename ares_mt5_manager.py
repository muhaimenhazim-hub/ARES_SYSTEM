"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 12: MULTI-TENANT AUTOMATIC MT5 INSTANCE MANAGER (ares_mt5_manager.py)
VERSION: 14.8 (EXACT MT5 CHART EA FORMAT, ISOLATED BINARIES & AUTO-COMPILE)
================================================================================
"""

import glob
import hashlib
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from ares_database import AresDatabaseManager

INSTANCES_DIR = "/root/mt5_instances"
BASE_MT5_DIR = "/root/.wine/drive_c/Program Files/MetaTrader 5"
GLOBAL_CONFIG_SRC = "/root/mt5_config"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

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
    دسکتاپ مجازی ایزوله Wine، کامپایل خودکار اکسپرت و تزریق دقیق چارت فعال.
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

    @staticmethod
    def _cred_hash(login: str, password: str, server: str) -> str:
        raw = f"{login}|{password}|{server}".encode("utf-8")
        return hashlib.md5(raw).hexdigest()

    def ensure_base_ea_compiled(self):
        """اطمینان از وجود نسخه کامپایل‌شده AresBridgeEA.ex5 متناسب با بیلد متاتریدر سرور"""
        src_mq5 = os.path.join(PROJECT_DIR, "AresBridgeEA.mq5")
        base_experts = os.path.join(BASE_MT5_DIR, "MQL5", "Experts")
        base_mq5 = os.path.join(base_experts, "AresBridgeEA.mq5")
        base_ex5 = os.path.join(base_experts, "AresBridgeEA.ex5")
        metaeditor = os.path.join(BASE_MT5_DIR, "MetaEditor64.exe")

        if not os.path.exists(src_mq5) or not os.path.exists(metaeditor):
            return

        need_compile = not os.path.exists(base_ex5)
        if not need_compile:
            try:
                if os.path.getmtime(src_mq5) > os.path.getmtime(base_ex5):
                    need_compile = True
            except Exception:
                pass

        if not need_compile:
            return

        try:
            os.makedirs(base_experts, exist_ok=True)
            shutil.copy2(src_mq5, base_mq5)
            print("🔨 [ARES CLOUD MANAGER]: در حال کامپایل AresBridgeEA.mq5 با متاادیتور سرور...", flush=True)
            cmd = (
                f"cd '{BASE_MT5_DIR}' && "
                f"DISPLAY=:99 WINEDEBUG=-all timeout 35 wine MetaEditor64.exe "
                f'/compile:"MQL5\\Experts\\AresBridgeEA.mq5" /log >/dev/null 2>&1'
            )
            subprocess.run(cmd, shell=True, check=False)
            if os.path.exists(base_ex5):
                print("✅ [ARES CLOUD MANAGER]: اکسپرت AresBridgeEA.ex5 با موفقیت در سرور کامپایل شد.", flush=True)
        except Exception as e:
            print(f"⚠️ [خطای کامپایل اکسپرت]: {e}", flush=True)

    def stop_login_instance(self, login: str):
        """توقف ایمن متاتریدر یک کاربر خاص (در صورت تغییر رمز یا سرور)"""
        clean_login = str(login).strip()
        user_dir = os.path.realpath(os.path.join(INSTANCES_DIR, clean_login))
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
                            os.kill(int(pid_str), 9)
                    except Exception:
                        pass
            subprocess.run(["pkill", "-9", "-f", f"MT5_{clean_login}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception:
            pass

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

    @staticmethod
    def _ensure_default_chart_with_ea(user_dir: str, symbol: str, user_identifier: str):
        """ساخت چارت پیش‌فرض با فرمت دقیق متاتریدر شامل path و expertmode=1"""
        charts_default_dir = os.path.join(user_dir, "MQL5", "Profiles", "Charts", "Default")
        os.makedirs(charts_default_dir, exist_ok=True)
        chart_path = os.path.join(charts_default_dir, "chart01.chr")

        needs_write = True
        if os.path.exists(chart_path):
            try:
                raw = open(chart_path, "rb").read()
                txt = raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:100] else "utf-8", errors="ignore")
                if (
                    "path=Experts\\AresBridgeEA.ex5" in txt
                    and "expertmode=1" in txt
                    and f"symbol={symbol}" in txt
                ):
                    needs_write = False
            except Exception:
                pass

        if not needs_write:
            return

        chart_content = f"""<chart>
id=128968168864101562
symbol={symbol}
period_type=0
period_size=15
digits=5
scale=4
mode=1
grid=1
volume=0
scroll=1
shift=0
shift_size=20.000000
one_click=0
window_type=1
background_color=0
foreground_color=16777215
barup_color=65280
bardown_color=65280
<expert>
name=AresBridgeEA
path=Experts\\AresBridgeEA.ex5
expertmode=1
<inputs>
InpServerURL=http://141.98.166.81/api/bridge/sync
InpUserIdentifier={user_identifier}
InpSyncSeconds=2
InpSlippagePoints=50
InpMaxOpenPositions=3
InpMaxLotCap=0.5
</inputs>
</expert>
<window>
height=100.000000
<indicator>
name=Main
</indicator>
</window>
</chart>
"""
        try:
            with open(chart_path, "w", encoding="utf-16") as f:
                f.write(chart_content)
        except Exception:
            pass

    def setup_user_environment(self, user: Dict[str, Any]) -> Optional[str]:
        """آماده‌سازی خودکار پوشه ایزوله و فایل کانفیگ برای هر بروکر در دنیا"""
        login = str(user.get("mt5_login", "")).strip()
        password = str(user.get("mt5_pass", "")).strip()
        server_raw = str(user.get("mt5_server", "MetaQuotes-Demo")).strip() or "MetaQuotes-Demo"
        identifier = str(user.get("identifier", "")).strip() or login

        if not login or not password:
            return None

        self.ensure_base_ea_compiled()

        # تبدیل هوشمند نام بروکر به نام رسمی داخل servers.dat
        server_lower = server_raw.lower()
        server_endpoint = UNIVERSAL_BROKER_MAP.get(server_lower, server_raw)

        user_dir = os.path.join(INSTANCES_DIR, login)
        config_dir = os.path.join(user_dir, "config")
        experts_dir = os.path.join(user_dir, "MQL5", "Experts")

        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(experts_dir, exist_ok=True)

        # حذف لینک قدیمی پوشه Profiles در صورت وجود تا پروفایل اختصاصی کاربر اجرا شود
        for old_prof in ["Profiles", "profiles"]:
            old_prof_path = os.path.join(user_dir, old_prof)
            if os.path.islink(old_prof_path):
                try:
                    os.unlink(old_prof_path)
                except Exception:
                    pass

        # ۱. کپی ایزوله فایل‌های اجرایی متاتریدر (بدون هاردلینک جهت جلوگیری از قفل Error 32)
        if os.path.exists(BASE_MT5_DIR):
            for fname in os.listdir(BASE_MT5_DIR):
                src = os.path.join(BASE_MT5_DIR, fname)
                dst = os.path.join(user_dir, fname)
                if os.path.isfile(src) and (fname.lower().endswith(".exe") or fname.lower().endswith(".dll")):
                    try:
                        need_copy = not os.path.exists(dst)
                        if not need_copy:
                            st_src = os.stat(src)
                            st_dst = os.stat(dst)
                            if st_dst.st_nlink > 1 or st_dst.st_size != st_src.st_size:
                                os.remove(dst)
                                need_copy = True
                        if need_copy:
                            shutil.copy2(src, dst)
                    except Exception:
                        pass

            for folder in ["Templates", "templates", "Help", "help", "Sounds", "sounds", "Bases", "bases"]:
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

        # ۲. قرار دادن جدیدترین اکسپرت کامپایل‌شده سرور در پوشه کاربر
        ea_sources = [
            os.path.join(BASE_MT5_DIR, "MQL5", "Experts", "AresBridgeEA.ex5"),
            os.path.join(PROJECT_DIR, "AresBridgeEA.ex5"),
        ]
        target_ea = os.path.join(experts_dir, "AresBridgeEA.ex5")
        for src_ea in ea_sources:
            if os.path.exists(src_ea):
                try:
                    shutil.copy2(src_ea, target_ea)
                    break
                except Exception:
                    pass

        src_mq5 = os.path.join(PROJECT_DIR, "AresBridgeEA.mq5")
        if os.path.exists(src_mq5):
            try:
                shutil.copy2(src_mq5, os.path.join(experts_dir, "AresBridgeEA.mq5"))
            except Exception:
                pass

        # ۳. انتقال کانفیگ سرورها
        if os.path.exists(GLOBAL_CONFIG_SRC):
            subprocess.run(f"cp -rf '{GLOBAL_CONFIG_SRC}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)
        for base_cfg_name in ["Config", "config"]:
            base_config = os.path.join(BASE_MT5_DIR, base_cfg_name)
            if os.path.exists(base_config):
                subprocess.run(f"cp -n '{base_config}'/* '{config_dir}/' 2>/dev/null", shell=True, check=False)

        # ۴. انتخاب هوشمند نماد استارت متناسب با بروکر و تزریق چارت پیش‌فرض با اکسپرت متصل
        start_symbol = "EURUSD." if "aron" in server_lower else "EURUSD"
        self._ensure_default_chart_with_ea(user_dir, start_symbol, identifier)

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
WebRequest=1
WebRequestUrl=http://141.98.166.81,http://127.0.0.1,http://localhost

[Start]
Expert=AresBridgeEA
Symbol={start_symbol}
Period=M15
"""
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        # ثبت هش مشخصات ورود فعلی برای تشخیص تغییرات بعدی کاربر
        cred_file = os.path.join(user_dir, ".cred_hash")
        with open(cred_file, "w", encoding="utf-8") as f:
            f.write(self._cred_hash(login, password, server_endpoint))

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
            f"DISPLAY=:99 WINEDEBUG=-all nohup wine explorer /desktop={desktop_name},1280x1024 terminal64.exe /portable /config:mt5_start.ini > '{wine_log}' 2>&1 & "
            f"echo $! > '{pid_file}'"
        )

        print(f"🚀 [ARES CLOUD MANAGER]: در حال اجرای متاتریدر اکانت {login} ({server}) روی دسکتاپ {desktop_name}...", flush=True)
        try:
            subprocess.run(launch_cmd, shell=True, check=False)
            dismiss_cmd = "(sleep 5 && DISPLAY=:99 xdotool key Escape Return 2>/dev/null; sleep 10 && DISPLAY=:99 xdotool key Escape 2>/dev/null) &"
            subprocess.run(dismiss_cmd, shell=True, check=False)
            return True
        except Exception as e:
            print(f"⚠️ [خطا در اتصال اکانت {login}]: {e}", flush=True)
            return False

    def sync_all_user_instances(self):
        """رصد دائم، تشخیص تغییر اطلاعات حساب و روشن کردن متاتریدر کاربران"""
        accounts = self.get_configured_accounts()
        for user in accounts:
            login = str(user.get("mt5_login", "")).strip()
            password = str(user.get("mt5_pass", "")).strip()
            server_raw = str(user.get("mt5_server", "MetaQuotes-Demo")).strip() or "MetaQuotes-Demo"
            server_endpoint = UNIVERSAL_BROKER_MAP.get(server_raw.lower(), server_raw)
            if not login or not password:
                continue

            if self.is_login_running(login):
                cred_file = os.path.join(INSTANCES_DIR, login, ".cred_hash")
                if os.path.exists(cred_file):
                    try:
                        saved_hash = open(cred_file, "r", encoding="utf-8").read().strip()
                        if saved_hash != self._cred_hash(login, password, server_endpoint):
                            print(f"🔄 [ARES CLOUD MANAGER]: تغییر رمز/سرور برای {login} شناسایی شد؛ ری‌استارت اکانت...", flush=True)
                            self.stop_login_instance(login)
                            time.sleep(2)
                            self.launch_instance(user)
                            time.sleep(3)
                    except Exception:
                        pass
                continue

            self.launch_instance(user)
            time.sleep(3)

    def run_supervisor(self, poll_interval_seconds: int = 10):
        print("=" * 80, flush=True)
        print("🌟 ناظر هوشمند ابری متاتریدرها (ARES V14.8 - فرمت دقیق چارت اکسپرت) فعال شد.", flush=True)
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