"""
================================================================================
ARES AI TRADING SYSTEM
CENTRAL ACCOUNT & BROKER CONFIGURATION
VERSION: 2.0 (GUI-CONTROLLED)
================================================================================
"""

import json
import os

CONFIG_FILE = "ares_user_config.json"

DEFAULT_CONFIG = {
    "trading_mode": "PAPER",
    "binance": {
        "api_key": "",
        "secret_key": "",
        "testnet": False
    },
    "mt5": {
        "account_number": "",
        "password": "",
        "server": ""
    }
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)