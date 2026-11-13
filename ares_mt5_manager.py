"""
================================================================================
ARES AI TRADING SYSTEM
PHASE 12: MULTI-TENANT AUTOMATIC MT5 INSTANCE MANAGER (ares_mt5_manager.py)
VERSION: 15.0 (ARONMARKETS SERVERS.DAT, CLEAN CONFIG ISOLATION & CLOUD FILE BRIDGE)
================================================================================
"""

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

import requests

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
    دسکتاپ مجازی ایزوله Wine، کامپایل خودکار اکسپرت و پل ابری ضدخطای ۴۰۱۴.
    """

    def __init__(self, db: Optional[AresDatabaseManager] = None):
        self.db = db or AresDatabaseManager()
        os.makedirs(INSTANCES_DIR, exist_ok=True)
        self._poisoned_hashes = self._compute_poisoned_hashes()

    @staticmethod
    def _file_md5(path: str) -> str:
        if not os.path.exists(path):
            return ""
        try:
            h = hashlib.md5()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return ""

    def _compute_poisoned_hashes(self) -> Dict[str, str]:
        return {
            "accounts.dat": self._file_md5(os.path.join(GLOBAL_CONFIG_SRC, "accounts.dat")),
            "common.ini": self._file_md5(os.path.join(GLOBAL_CONFIG_SRC, "common.ini")),
        }

    def get_configured_accounts(self) -> List[Dict[str, Any]]:
        """دریافت تمام حساب‌های متاتریدر ثبت‌شده توسط کاربران از دیتابیس"""
        try:
            return self.db.get_all_mt5_configured_users()
        except Exception as e:
            print(f"⚠️ [خطای دیتابیس در خواندن حساب‌ها]: {e}", flush=True)
            return []

    def _get_base_ea_stamp(self) -> str:
        base_ex5 = os.path.join(BASE_MT5_DIR, "MQL5", "Experts", "AresBridgeEA.ex5")
        if os.path.exists(base_ex5):
            try:
                return str(int(os.path.getmtime(base_ex5)))
            except Exception:
                pass
        return "0"

    @staticmethod
    def _cred_hash(login: str, password: str, server: str, ea_stamp: str = "0") -> str:
        raw = f"V15|{login}|{password}|{server}|{ea_stamp}".encode("utf-8")
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
        """توقف ایمن متاتریدر یک کاربر خاص (هنگام قطع ارتباط یا تغییر رمز/سرور)"""
        clean_login = str(login).strip()
        user_dir = os.path.realpath(os.path.join(INSTANCES_DIR, clean_login))
        pid_file = os.path.join(user_dir, "mt5.pid")
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
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception:
            pass

    def is_login_running(self, login: str) -> bool:
        """بررسی دقیق روشن بودن متاتریدر کاربر بدون اجازه به اجرای تکراری"""
        clean_login = str(login).strip()
        if not clean_login:
            return False

        user_dir = os.path.realpath(os.path.join(INSTANCES_DIR, clean_login))
        pid_file = os.path.join(user_dir, "mt5.pid")

        try:
            res = subprocess.run(["pgrep", "-f", f"MT5_{clean_login}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and res.stdout.strip():
                return True
        except Exception:
            pass

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
        """ساخت چارت پیش‌فرض با فرمت دقیق متاتریدر شامل path، expertmode=1 و شناسه کاربر"""
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
                    and f"InpUserIdentifier={user_identifier}" in txt
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

    def _clean_poisoned_user_configs(self, config_dir: str, login: str):
        """حذف فایل‌های قدیمی کپی‌شده از ویندوز جهت جلوگیری از خطای امنیتی حساب و قفل شدن اکانت قبلی"""
        acc_file = os.path.join(config_dir, "accounts.dat")
        if os.path.exists(acc_file) and self._poisoned_hashes.get("accounts.dat"):
            if self._file_md5(acc_file) == self._poisoned_hashes["accounts.dat"]:
                try:
                    os.remove(acc_file)
                except Exception:
                    pass

        common_file = os.path.join(config_dir, "common.ini")
        if os.path.exists(common_file):
            should_remove = False
            if self._poisoned_hashes.get("common.ini") and self._file_md5(common_file) == self._poisoned_hashes["common.ini"]:
                should_remove = True
            else:
                try:
                    raw = open(common_file, "rb").read()
                    txt = raw.decode("utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in raw[:100] else "utf-8", errors="ignore")
                    if "6FD26B4E5B59" in txt or (f"Login={login}" not in txt and "Login=300260" in txt):
                        should_remove = True
                except Exception:
                    pass
            if should_remove:
                try:
                    os.remove(common_file)
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

        server_lower = server_raw.lower()
        server_endpoint = UNIVERSAL_BROKER_MAP.get(server_lower, server_raw)

        user_dir = os.path.join(INSTANCES_DIR, login)
        config_dir = os.path.join(user_dir, "config")
        experts_dir = os.path.join(user_dir, "MQL5", "Experts")
        files_dir = os.path.join(user_dir, "MQL5", "Files")

        os.makedirs(config_dir, exist_ok=True)
        os.makedirs(experts_dir, exist_ok=True)
        os.makedirs(files_dir, exist_ok=True)

        for old_prof in ["Profiles", "profiles"]:
            old_prof_path = os.path.join(user_dir, old_prof)
            if os.path.islink(old_prof_path):
                try:
                    os.unlink(old_prof_path)
                except Exception:
                    pass

        # ۱. کپی ایزوله فایل‌های اجرایی متاتریدر (بدون بازگرداندن بیلد آپدیت‌شده)
        if os.path.exists(BASE_MT5_DIR):
            for fname in os.listdir(BASE_MT5_DIR):
                src = os.path.join(BASE_MT5_DIR, fname)
                dst = os.path.join(user_dir, fname)
                if os.path.isfile(src) and (fname.lower().endswith(".exe") or fname.lower().endswith(".dll")):
                    try:
                        need_copy = not os.path.exists(dst)
                        if not need_copy:
                            st_dst = os.stat(dst)
                            if st_dst.st_nlink > 1:
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

        # ۳. پاکسازی فایل‌های قدیمی و کپی اختصاصی سرورهای بروکر (servers.dat و certificates)
        self._clean_poisoned_user_configs(config_dir, login)

        aron_servers = os.path.join(GLOBAL_CONFIG_SRC, "servers_aronmarkets.dat")
        default_servers = os.path.join(GLOBAL_CONFIG_SRC, "servers.dat")
        target_servers = os.path.join(config_dir, "servers.dat")

        if "aron" in server_lower and os.path.exists(aron_servers):
            try:
                shutil.copy2(aron_servers, target_servers)
            except Exception:
                pass
        elif os.path.exists(default_servers) and not os.path.exists(target_servers):
            try:
                shutil.copy2(default_servers, target_servers)
            except Exception:
                pass

        src_certs = os.path.join(GLOBAL_CONFIG_SRC, "certificates")
        dst_certs = os.path.join(config_dir, "certificates")
        if os.path.exists(src_certs) and not os.path.exists(dst_certs):
            try:
                shutil.copytree(src_certs, dst_certs, dirs_exist_ok=True)
            except Exception:
                pass

        for base_cfg_name in ["Config", "config"]:
            base_config = os.path.join(BASE_MT5_DIR, base_cfg_name)
            base_srv = os.path.join(base_config, "servers.dat")
            if os.path.exists(base_srv) and not os.path.exists(target_servers):
                try:
                    shutil.copy2(base_srv, target_servers)
                except Exception:
                    pass

        # ۴. انتخاب هوشمند نماد استارت متناسب با بروکر و تزریق چارت پیش‌فرض با اکسپرت متصل
        start_symbol = "EURUSD." if "aron" in server_lower else "EURUSD"
        self._ensure_default_chart_with_ea(user_dir, start_symbol, identifier)

        # ۵. ساخت فایل کانفیگ استارت متاتریدر با بخش رسمی [StartUp]
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
WebRequestUrl=http://141.98.166.81

[StartUp]
Expert=AresBridgeEA
Symbol={start_symbol}
Period=M15
"""
        with open(ini_path, "w", encoding="utf-8") as f:
            f.write(ini_content)

        cred_file = os.path.join(user_dir, ".cred_hash")
        with open(cred_file, "w", encoding="utf-8") as f:
            f.write(self._cred_hash(login, password, server_endpoint, self._get_base_ea_stamp()))

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

    def process_local_file_bridges(self):
        """پل ارتباطی فایل محلی برای انتقال تیک‌ها و دستورات متاتریدرهای ابری بدون محدودیت ۴۰۱۴"""
        if not os.path.exists(INSTANCES_DIR):
            return

        port = os.environ.get("PORT", "80")
        sync_url = f"http://127.0.0.1:{port}/api/bridge/sync"

        for entry in os.listdir(INSTANCES_DIR):
            files_dir = os.path.join(INSTANCES_DIR, entry, "MQL5", "Files")
            out_file = os.path.join(files_dir, "ares_sync_out.json")
            if not os.path.exists(out_file):
                continue

            reading_file = os.path.join(files_dir, "ares_sync_out.reading")
            try:
                os.replace(out_file, reading_file)
                with open(reading_file, "r", encoding="utf-8", errors="ignore") as f:
                    payload = json.load(f)
            except Exception:
                continue
            finally:
                if os.path.exists(reading_file):
                    try:
                        os.remove(reading_file)
                    except Exception:
                        pass

            if not isinstance(payload, dict):
                continue
            login_str = str(payload.get("login", "")).strip()
            if login_str in ("", "0"):
                continue

            try:
                resp = requests.post(sync_url, json=payload, timeout=3.0)
                if resp.status_code == 200:
                    resp_data = resp.json()
                    new_orders = resp_data.get("orders", [])
                    if isinstance(new_orders, list) and new_orders:
                        in_file = os.path.join(files_dir, "ares_sync_in.json")
                        in_tmp = os.path.join(files_dir, "ares_sync_in.tmp")
                        merged_orders: List[Dict[str, Any]] = []
                        if os.path.exists(in_file):
                            try:
                                with open(in_file, "r", encoding="utf-8") as f:
                                    prev = json.load(f)
                                    if isinstance(prev.get("orders"), list):
                                        merged_orders.extend(prev["orders"])
                            except Exception:
                                pass
                        merged_orders.extend(new_orders)
                        with open(in_tmp, "w", encoding="utf-8") as f:
                            json.dump({"status": "SYNCED", "orders": merged_orders}, f, ensure_ascii=False, separators=(",", ":"))
                        os.replace(in_tmp, in_file)
            except Exception:
                pass

    def run_file_bridge_loop(self):
        while True:
            try:
                self.process_local_file_bridges()
            except Exception:
                pass
            time.sleep(1.0)

    def sync_all_user_instances(self):
        """رصد دائم، توقف اکانت‌های قطع‌شده، تشخیص تغییر اکسپرت/رمز و اجرای نوبتی جهت حفظ CPU"""
        self.ensure_base_ea_compiled()
        ea_stamp = self._get_base_ea_stamp()

        accounts = self.get_configured_accounts()
        active_logins = {
            str(u.get("mt5_login", "")).strip()
            for u in accounts
            if str(u.get("mt5_login", "")).strip() and str(u.get("mt5_pass", "")).strip()
        }

        if os.path.exists(INSTANCES_DIR):
            for entry in os.listdir(INSTANCES_DIR):
                entry_path = os.path.join(INSTANCES_DIR, entry)
                if os.path.isdir(entry_path) and entry not in active_logins:
                    if self.is_login_running(entry):
                        print(f"🛑 [ARES CLOUD MANAGER]: توقف متاتریدر اکانت قطع‌شده ({entry})...", flush=True)
                        self.stop_login_instance(entry)

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
                        if saved_hash != self._cred_hash(login, password, server_endpoint, ea_stamp):
                            print(f"🔄 [ARES CLOUD MANAGER]: تغییر رمز/سرور یا آپدیت اکسپرت برای {login}؛ ری‌استارت اکانت...", flush=True)
                            self.stop_login_instance(login)
                            time.sleep(2)
                            self.launch_instance(user)
                            break
                    except Exception:
                        pass
                continue

            self.launch_instance(user)
            break

    def run_supervisor(self, poll_interval_seconds: int = 10):
        print("=" * 80, flush=True)
        print("🌟 ناظر هوشمند ابری متاتریدرها (ARES V15.0 - سرورهای آرون‌مارکتس، پل ابری ضد ۴۰۱۴ و ایزوله‌سازی کامل) فعال شد.", flush=True)
        print("=" * 80, flush=True)

        bridge_thread = threading.Thread(target=self.run_file_bridge_loop, daemon=True)
        bridge_thread.start()

        while True:
            try:
                self.sync_all_user_instances()
            except Exception as e:
                print(f"⚠️ [خطای ناظر ابری]: {e}", flush=True)
            time.sleep(poll_interval_seconds)


if __name__ == "__main__":
    manager = AresMT5MultiManager()
    manager.run_supervisor()