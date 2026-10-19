"""
Configuration for PlayStation Gift Card Stock Monitor.
Define target websites, CSS selectors, alert thresholds, and Replit runtime settings.
"""

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# 1. Telegram Credentials (Replit Secrets / .env)
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# ==========================================
# 2. Monitoring & Bot Behavior Settings
# ==========================================
# Interval between monitoring loops in seconds (e.g. 180s = 3 mins, 240s = 4 mins)
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "240"))

# Delay between checking each website to prevent CPU spikes and rate limits (seconds)
SITE_CHECK_DELAY_SECONDS = int(os.getenv("SITE_CHECK_DELAY_SECONDS", "4"))

# If True, sends an alert on startup for any items currently In Stock (Default: True)
NOTIFY_ON_INITIAL_RUN = os.getenv("NOTIFY_ON_INITIAL_RUN", "True").lower() in ("true", "1", "yes")

# Send a startup confirmation message to Telegram when the script launches
SEND_STARTUP_MESSAGE = os.getenv("SEND_STARTUP_MESSAGE", "True").lower() in ("true", "1", "yes")

# Send a full stock summary report to Telegram after the first check cycle
SEND_INITIAL_SUMMARY = os.getenv("SEND_INITIAL_SUMMARY", "True").lower() in ("true", "1", "yes")

# Heartbeat interval in cycles (90 cycles * 4 mins = ~6 hours). Set to 0 to disable
HEARTBEAT_CYCLE_INTERVAL = int(os.getenv("HEARTBEAT_CYCLE_INTERVAL", "90"))

# Browser timeout in milliseconds
PAGE_TIMEOUT_MS = int(os.getenv("PAGE_TIMEOUT_MS", "35000"))

# State persistence file
STATE_FILE_PATH = os.getenv("STATE_FILE_PATH", "stock_state.json")

# Built-in Keep-Alive Web Server port (for UptimeRobot pinging on Replit)
KEEP_ALIVE_PORT = int(os.getenv("PORT", "8080"))

# Block heavy media resources in Playwright (images, css, fonts) to keep Replit RAM < 150MB
BLOCK_MEDIA_RESOURCES = True

# ==========================================
# 3. Target Store Configurations
# ==========================================
TARGET_SITES = [
    {
        "id": "rooter_psn_1000",
        "platform": "Rooter Shop",
        "item_name": "PlayStation Network ₹1,000 Voucher",
        "url": "https://shop.rooter.gg",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "currently unavailable", "notify me"],
        "in_stock_keywords": ["buy now", "add to cart", "purchase", "redeem"],
        "container_selector": "button, div[class*='card'], div[class*='product']",
        "price_selector": "span[class*='price'], div[class*='price']",
        "enabled": True,
    },
    {
        "id": "gamestheshop_psn_1000",
        "platform": "Games The Shop",
        "item_name": "PlayStation Store ₹1,000 Gift Card",
        "url": "https://www.gamestheshop.com/playstation-store-gift-cards",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "notify when in stock"],
        "in_stock_keywords": ["add to cart", "buy now", "in stock"],
        "container_selector": ".product-layout, .detail-pro-info, .btn-add-cart",
        "price_selector": ".price, .special-price",
        "enabled": True,
    },
    {
        "id": "jiogames_psn_store",
        "platform": "JioGames",
        "item_name": "PlayStation Store Voucher (JioGames)",
        "url": "https://jiogames.com",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "coming soon"],
        "in_stock_keywords": ["buy now", "get voucher", "add to cart"],
        "container_selector": "body",
        "price_selector": "",
        "enabled": True,
    },
    {
        "id": "hubble_psn_vouchers",
        "platform": "Hubble",
        "item_name": "PlayStation E-Gift Card (Hubble)",
        "url": "https://myhubble.money",
        "engine": "playwright",
        "wait_selector": "body",
        "out_of_stock_keywords": ["out of stock", "sold out", "unavailable"],
        "in_stock_keywords": ["buy now", "purchase", "get card", "avail"],
        "container_selector": "body",
        "price_selector": "",
        "enabled": True,
    },
    {
        "id": "mx2games_psn_1000",
        "platform": "MX2Games",
        "item_name": "PlayStation Network PSN Wallet Top-Up (India)",
        "url": "https://mx2games.com/product/playstation-network-psn-wallet-top-up-card-inr-india/",
        "engine": "requests",
        "wait_selector": "",
        "out_of_stock_keywords": ["out of stock", "sold out"],
        "in_stock_keywords": ["in stock", "add to cart"],
        "container_selector": ".stock, .single_add_to_cart_button",
        "price_selector": ".woocommerce-Price-amount",
        "enabled": True,
    },
]
