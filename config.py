"""
Configuration for PlayStation Gift Card Stock Monitor.
Define target websites, CSS selectors, alert thresholds, and Replit/Railway runtime settings.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# 1. Telegram Credentials (Railway / Replit Secrets / .env)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ==========================================
# 2. Monitoring & Bot Behavior Settings
# ==========================================
# Interval between monitoring loops in seconds (Default: 60s = 1 min for instant restock detection)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))


# Delay between checking each website to prevent CPU spikes and rate limits (seconds)
SITE_CHECK_DELAY_SECONDS = int(os.getenv("SITE_CHECK_DELAY_SECONDS", "4"))

# If True, sends an alert on startup for any items currently In Stock (Default: True)
NOTIFY_ON_INITIAL_RUN = os.getenv("NOTIFY_ON_INITIAL_RUN", "True").lower() in ("true", "1", "yes")

# Send a startup confirmation message to Telegram when the script launches
SEND_STARTUP_MESSAGE = os.getenv("SEND_STARTUP_MESSAGE", "True").lower() in ("true", "1", "yes")

# Send a full stock summary report to Telegram after the first check cycle
SEND_INITIAL_SUMMARY = os.getenv("SEND_INITIAL_SUMMARY", "True").lower() in ("true", "1", "yes")

# Send regular periodic summary update report every 360 cycles
PERIODIC_SUMMARY_CYCLES = int(os.getenv("PERIODIC_SUMMARY_CYCLES", "360"))

# Heartbeat interval every 360 cycles. Set to 0 to disable
HEARTBEAT_CYCLE_INTERVAL = int(os.getenv("HEARTBEAT_CYCLE_INTERVAL", "360"))



# Browser timeout in milliseconds (increased to 45s for reliable cloud rendering)
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "45000"))

# State persistence file
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "stock_state.json")

# Built-in Keep-Alive Web Server port (Railway / Replit default: 8080)
KEEP_ALIVE_PORT = int(os.getenv("PORT", "8080"))

# Block heavy media resources in Playwright (images, fonts, media) to keep RAM < 150MB
BLOCK_MEDIA_RESOURCES = True

# ==========================================
# 3. Target Store Configurations (Direct PlayStation Voucher URLs)
# ==========================================
TARGET_SITES = [
    {
        "id": "rooter_psn",
        "platform": "Rooter Shop",
        "item_name": "PlayStation Network Wallet Voucher",
        # Direct product URL for PlayStation cards on Rooter
        "url": "https://shop.rooter.gg/product/playstation-gift-cards",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "currently unavailable"],
        "in_stock_keywords": ["wallet code", "proceed to pay", "pay via wallet", "pay ₹", "pay rs", "add address", "buy now", "in stock"],
        "container_selector": "body",
        "price_selector": "span[class*='price'], div[class*='price']",
        "enabled": True,
    },
    {
        "id": "gamestheshop_psn",
        "platform": "Games The Shop",
        "item_name": "PlayStation Store Gift Cards",
        # Direct PlayStation store digital products search on GTS
        "url": "https://www.gamestheshop.com/search?condition=Digital&platforms=PlayStation%2CPS5%2CPS4%2CPSN",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "notify when in stock", "notify me", "currently unavailable", "(0)"],
        "in_stock_keywords": ["add to cart", "buy now", "buy digital"],
        "container_selector": "body",
        "price_selector": ".price, .special-price",
        "enabled": True,
    },
    {
        "id": "jiogames_psn_store",
        "platform": "JioGames Store",
        "item_name": "PlayStation Wallet Voucher",
        # Direct JioGames store products catalogue
        "url": "https://store.jiogames.com/products",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "coming soon"],
        "in_stock_keywords": ["playstation", "buy now", "get voucher", "add to cart"],
        "container_selector": "body",
        "price_selector": "",
        "enabled": True,
    },
]

