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

# Guaranteed default recipient Chat IDs (Aakash: 5701727023, Ajay: 1988639571)
DEFAULT_RECIPIENT_IDS = ["5701727023", "1988639571"]

# Read from env if provided, and merge with default recipients so both always receive messages
_env_cids = [cid.strip() for cid in os.getenv("TELEGRAM_CHAT_ID", "").split(",") if cid.strip()]
TELEGRAM_CHAT_IDS = list(dict.fromkeys(_env_cids + DEFAULT_RECIPIENT_IDS))
TELEGRAM_CHAT_ID = ",".join(TELEGRAM_CHAT_IDS)

# ==========================================
# 2. Monitoring & Bot Behavior Settings
# ==========================================
# Interval between monitoring loops in seconds (Default: 30s for ultra-fast restock detection)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))

# Delay between checking each website to prevent CPU spikes (seconds)
SITE_CHECK_DELAY_SECONDS = int(os.getenv("SITE_CHECK_DELAY_SECONDS", "2"))

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
        "in_stock_keywords": ["proceed to pay", "pay ₹", "pay rs", "add address"],
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
        "out_of_stock_keywords": ["in stock only (0)", "currently out of stock", "sold out", "out of stock", "(0)"],
        "in_stock_keywords": ["in stock only (1)", "in stock only (2)", "in stock only (3)", "in stock only (4)", "in stock only (5)"],
        "container_selector": "body",
        "price_selector": ".price, .special-price",
        "enabled": True,
    },
    {
        "id": "digistore_psn",
        "platform": "Digistore",
        "item_name": "PlayStation Network Wallet Topup",
        # Direct PlayStation cards on Digistore India (Nodwin Gaming)
        "url": "https://digistore.co.in/product-category/console-games/playstation-card/",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "currently unavailable"],
        "in_stock_keywords": ["add to cart", "buy now", "select options"],
        "container_selector": "body",
        "price_selector": ".price, span.woocommerce-Price-amount",
        "enabled": True,
    },
    {
        "id": "blinkit_psn",
        "platform": "Blinkit",
        "item_name": "Sony PlayStation Instant Voucher (Mumbai)",
        # Direct Blinkit PlayStation Instant Voucher search in Mumbai
        "url": "https://blinkit.com/s/?q=playstation+voucher",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "currently unavailable"],
        "in_stock_keywords": ["add", "add to cart"],
        "container_selector": "body",
        "price_selector": "",
        "min_interval_seconds": 60,
        "enabled": True,
    },
    {
        "id": "flipkart_psn",
        "platform": "Flipkart",
        "item_name": "PlayStation Network Wallet Voucher",
        # Direct Flipkart digital PlayStation gift cards catalog
        "url": "https://www.flipkart.com/search?q=playstation+network+wallet+voucher",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["currently unavailable", "coming soon", "out of stock"],
        "in_stock_keywords": ["buy now", "add to cart"],
        "container_selector": "body",
        "price_selector": "",
        "min_interval_seconds": 120,  # 2 minute cooling period to prevent captchas
        "enabled": True,
    },
]

