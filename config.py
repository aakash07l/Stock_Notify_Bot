"""
Configuration for PlayStation Gift Card Stock Monitor & Trigger Dispatcher (Bot 1).
Monitors Rooter Shop 24/7 without authentication, alerts Telegram, and instantly triggers Buy Bot (Bot 2).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# ==========================================
# 1. Telegram Credentials (Stock Tracker Bot)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8971931761:AAHZEBDz0QCq6WadUQa8Foiw4Gc0mtU_Css").strip()

# Target Telegram Chat IDs (Aakash & Ajay)
DEFAULT_RECIPIENT_IDS = ["5701727023", "1988639571"]
_env_cids = [cid.strip() for cid in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()]
TELEGRAM_CHAT_IDS = list(dict.fromkeys(_env_cids + DEFAULT_RECIPIENT_IDS))
TELEGRAM_CHAT_ID = ",".join(TELEGRAM_CHAT_IDS)

# ==========================================
# 2. Inter-Bot Webhook Communication (Bot 1 -> Bot 2)
# ==========================================
# Local HTTP Webhook to trigger Bot 2 on the same AWS EC2 machine (<2ms latency)
BUY_BOT_WEBHOOK_URL = os.getenv("BUY_BOT_WEBHOOK_URL", "http://127.0.0.1:5000/webhook/stock").strip()
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "psn_sniper_secret_key_2026").strip()

# ==========================================
# 3. Restock Target & Monitoring Settings
# ==========================================
# Target Denomination: 1000 (₹1,000 PlayStation Card)
TARGET_DENOMINATION = int(os.getenv("TARGET_DENOMINATION", "1000"))
# Target Quantity to buy: 2 cards = ₹2,000
TARGET_QUANTITY = int(os.getenv("TARGET_QUANTITY", "2"))

# Interval between checks in seconds (3 seconds for ultra-fast restock detection)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "3"))

# Alert cooldown in seconds (avoids repeating spam alerts while stock remains active)
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "90"))

# State persistence
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "stock_state.json")

# Built-in Keep-Alive / Health Check Web Server
KEEP_ALIVE_PORT = int(os.getenv("PORT", "8080"))

# ==========================================
# 4. Target Stores Configuration
# ==========================================
ROOTER_PSN_URL = "https://shop.rooter.gg/product/playstation-gift-cards"

TARGET_SITES = [
    {
        "id": "rooter_psn",
        "platform": "Rooter Shop",
        "item_name": "PlayStation Network Wallet Voucher",
        "url": ROOTER_PSN_URL,
        "enabled": True,
    }
]
