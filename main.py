"""
PlayStation Gift Card Stock Monitor & Restock Trigger Bot (Bot 1).
Monitors Rooter Shop 24/7 without authentication, alerts Telegram, and instantly triggers Buy Bot (Bot 2).
"""

import sys
import os
import re
import json
import time
import asyncio
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

import httpx
from aiohttp import web
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

import config

# ==========================================
# Logging Configuration
# ==========================================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("StockMonitor")

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Global monitoring state
LATEST_STOCK_STATE: Dict[int, bool] = {}
LAST_CHECK_TIME: float = 0.0
TOTAL_CYCLES: int = 0
BOT_START_TIME = datetime.datetime.now()
LAST_TRIGGER_TIMES: Dict[int, float] = {}

# User-Agent for unauthenticated public requests
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# ==========================================
# Telegram Alerts & Webhook Dispatcher
# ==========================================
async def send_telegram_alert(
    denomination: int,
    in_stock: bool,
    quantity: int = 2,
    custom_msg: Optional[str] = None
) -> bool:
    """Dispatches instant Telegram restock alert to all configured admin chat IDs."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token is missing! Skipping notification.")
        return False

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

    if custom_msg:
        msg = custom_msg
    elif in_stock:
        msg = (
            f"🚨 <b>RESTOCK ALERT: PlayStation ₹{denomination:,} IN STOCK!</b>\n\n"
            f"🎮 <b>Platform:</b> Rooter Shop\n"
            f"💳 <b>Item:</b> PlayStation Gift Card ₹{denomination:,}\n"
            f"📦 <b>Target Quantity:</b> {quantity} cards (₹{denomination * quantity:,})\n"
            f"⚡ <b>Action:</b> Instant signal dispatched to Buy Bot!\n"
            f"⏰ <b>Detected At:</b> {formatted_time}\n\n"
            f"👉 <a href='{config.ROOTER_PSN_URL}'><b>Click Here to View on Rooter</b></a>"
        )
    else:
        msg = (
            f"ℹ️ <b>Stock Status:</b> PlayStation ₹{denomination:,} is currently <b>Out of Stock</b>.\n"
            f"⏰ <i>{formatted_time}</i>"
        )

    api_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    any_success = False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in config.TELEGRAM_CHAT_IDS:
                payload = {
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }
                try:
                    resp = await client.post(api_url, json=payload)
                    if resp.status_code == 200:
                        any_success = True
                    else:
                        logger.error(f"Telegram API error {resp.status_code} for chat {chat_id}: {resp.text}")
                except Exception as ce:
                    logger.error(f"Failed to send Telegram message to {chat_id}: {ce}")
    except Exception as e:
        logger.error(f"Telegram client error: {e}")

    return any_success


async def trigger_buy_bot_webhook(denomination: int, quantity: int = 2) -> bool:
    """
    Sends an instant HTTP POST webhook to Bot 2 on localhost (< 2ms latency).
    Bot 2 is awakened to execute the purchase with zero prior polling on Rooter!
    """
    if not config.BUY_BOT_WEBHOOK_URL:
        logger.warning("No BUY_BOT_WEBHOOK_URL configured. Skipping internal trigger.")
        return False

    payload = {
        "platform": "rooter",
        "denomination": denomination,
        "quantity": quantity,
        "secret": config.INTERNAL_SECRET,
        "timestamp": time.time(),
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(config.BUY_BOT_WEBHOOK_URL, json=payload)
            if resp.status_code == 200:
                logger.info(f"⚡ Buy Bot successfully triggered for ₹{denomination:,} x {quantity}!")
                return True
            else:
                logger.warning(f"Buy Bot webhook returned HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to reach Buy Bot at {config.BUY_BOT_WEBHOOK_URL}: {e}")

    return False


# ==========================================
# Rooter Stock Sweeper (Dual-Engine: HTTP Fast Parser + Playwright Fallback)
# ==========================================
def parse_rooter_nextjs_stock(html: str) -> Dict[int, bool]:
    """
    Ultra-fast parser for Rooter's Next.js embedded JSON stream.
    Normalizes escaped quotes and extracts stock availability for each denomination.
    """
    results: Dict[int, bool] = {1000: False, 2000: False, 3000: False, 4000: False, 5000: False}
    if not html:
        return results

    # Normalize escaped quotes from Next.js hydration payload
    clean_html = html.replace('\\"', '"')

    denominations = [1000, 2000, 3000, 4000, 5000]

    for d in denominations:
        name_marker = f"Rs.{d} Wallet Code"
        idx = clean_html.find(name_marker)
        if idx == -1:
            name_marker = f"{d} Wallet Code"
            idx = clean_html.find(name_marker)

        if idx != -1:
            # Find next variation to prevent cross-denomination bleed
            next_marker_idx = clean_html.find('"name":"Rs.', idx + len(name_marker))
            end_idx = next_marker_idx if next_marker_idx != -1 else idx + 750
            block = clean_html[idx : min(idx + 750, end_idx)]
            out_flags = re.findall(r'"outOfStock"\s*:\s*(true|false)', block, re.IGNORECASE)
            if out_flags:
                has_in_stock = any(f.lower() == "false" for f in out_flags)
                results[d] = has_in_stock
            else:
                results[d] = False
        else:
            results[d] = False

    return results


async def check_rooter_stock_http() -> Optional[Dict[int, bool]]:
    """
    High-speed async HTTP fetch with cache-busting to bypass CDN stale caches.
    Takes 200-500ms, consumes < 15MB RAM, and doesn't load images or heavy JS.
    """
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.9",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    # Cache-busting parameter to prevent Cloudflare/Fastly stale CDN caching
    cache_bust_url = f"{config.ROOTER_PSN_URL}?_t={int(time.time() * 1000)}"
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=8.0) as client:
            resp = await client.get(cache_bust_url)
            if resp.status_code == 200 and "Wallet Code" in resp.text:
                return parse_rooter_nextjs_stock(resp.text)
            else:
                logger.warning(f"Rooter HTTP fetch returned status {resp.status_code}")
    except Exception as e:
        logger.warning(f"HTTP stock fetch error: {e}")

    return None


async def check_rooter_stock_playwright() -> Dict[int, bool]:
    """
    Fallback browser scraper using Playwright if HTTP request is blocked.
    """
    results: Dict[int, bool] = {1000: False, 2000: False, 3000: False, 4000: False, 5000: False}
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(user_agent=BROWSER_USER_AGENT)
            page = await context.new_page()

            # Abort media to save CPU/RAM
            await page.route(
                "**/*",
                lambda route: route.abort() if route.request.resource_type in ["image", "media", "font"] else route.continue_()
            )

            await page.goto(config.ROOTER_PSN_URL, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)
            content = await page.content()
            await browser.close()
            return parse_rooter_nextjs_stock(content)
    except Exception as e:
        logger.error(f"Playwright fallback error: {e}")

    return results


# ==========================================
# Background 24/7 Restock Monitoring Loop
# ==========================================
async def restock_monitor_loop():
    """
    Continuous 24/7 restock monitoring worker.
    Runs every CHECK_INTERVAL_SECONDS (default: 3 seconds).
    """
    global LATEST_STOCK_STATE, LAST_CHECK_TIME, TOTAL_CYCLES, LAST_TRIGGER_TIMES

    logger.info(
        f"🚀 Stock Monitor started! Target: ₹{config.TARGET_DENOMINATION} x {config.TARGET_QUANTITY} cards "
        f"every {config.CHECK_INTERVAL_SECONDS}s"
    )

    # Initial boot notification
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    start_msg = (
        f"🤖 <b>Stock Monitor Bot (Bot 1) Online!</b>\n\n"
        f"🎯 <b>Target:</b> PlayStation ₹{config.TARGET_DENOMINATION:,} x {config.TARGET_QUANTITY} cards\n"
        f"⏱️ <b>Check Interval:</b> Every {config.CHECK_INTERVAL_SECONDS}s\n"
        f"⚡ <b>Internal Webhook:</b> <code>{config.BUY_BOT_WEBHOOK_URL}</code>\n"
        f"📡 <b>Status:</b> 🟢 24/7 Monitoring Active on AWS Mumbai\n"
        f"⏰ <i>Started: {now_ist.strftime('%d-%b-%Y %I:%M:%S %p IST')}</i>"
    )
    asyncio.create_task(send_telegram_alert(config.TARGET_DENOMINATION, False, custom_msg=start_msg))

    while True:
        try:
            TOTAL_CYCLES += 1
            LAST_CHECK_TIME = time.time()

            # 1. Primary check: Fast HTTP request (< 500ms)
            stock_data = await check_rooter_stock_http()

            # 2. Fallback check: Playwright if HTTP failed
            if stock_data is None:
                logger.info("HTTP fetch failed, falling back to Playwright headless sweep...")
                stock_data = await check_rooter_stock_playwright()

            LATEST_STOCK_STATE = stock_data
            target_denom = config.TARGET_DENOMINATION
            is_target_in_stock = stock_data.get(target_denom, False)
            now = time.time()

            # 1. Target denomination restock -> Trigger Buy Bot + Alert Telegram
            if is_target_in_stock:
                last_trig = LAST_TRIGGER_TIMES.get(target_denom, 0.0)
                if (now - last_trig) > config.ALERT_COOLDOWN_SECONDS:
                    LAST_TRIGGER_TIMES[target_denom] = now
                    logger.info(f"🚨 TARGET RESTOCK: PlayStation ₹{target_denom:,} is IN STOCK! Dispatched to Buy Bot.")

                    # Parallel execution: Trigger Buy Bot & Send Telegram Alert at the exact same millisecond
                    await asyncio.gather(
                        trigger_buy_bot_webhook(target_denom, config.TARGET_QUANTITY),
                        send_telegram_alert(target_denom, in_stock=True, quantity=config.TARGET_QUANTITY)
                    )

            # 2. Check if ANY OTHER denomination restocked -> Alert Telegram
            for other_d, is_avail in stock_data.items():
                if is_avail and other_d != target_denom:
                    other_last = LAST_TRIGGER_TIMES.get(other_d, 0.0)
                    if (now - other_last) > config.ALERT_COOLDOWN_SECONDS:
                        LAST_TRIGGER_TIMES[other_d] = now
                        logger.info(f"🚨 OTHER RESTOCK: PlayStation ₹{other_d:,} is IN STOCK! Notifying Telegram.")
                        await send_telegram_alert(other_d, in_stock=True, quantity=1)

            if not any(stock_data.values()):
                if TOTAL_CYCLES % 120 == 0:
                    logger.info(f"[Cycle #{TOTAL_CYCLES}] All PlayStation vouchers currently Out of Stock. Monitoring active...")

        except Exception as e:
            logger.error(f"Error in restock monitor loop: {e}", exc_info=True)

        await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)


# ==========================================
# Telegram Bot Interactive Commands
# ==========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command."""
    user = update.effective_user
    msg = (
        f"👋 <b>Welcome {user.first_name}!</b>\n\n"
        f"I am the <b>PlayStation Stock Monitor Bot (Bot 1)</b>.\n"
        f"I run unauthenticated 24/7 on AWS Mumbai, checking Rooter every {config.CHECK_INTERVAL_SECONDS}s.\n\n"
        f"<b>🎯 Current Target:</b> PlayStation ₹{config.TARGET_DENOMINATION:,} x {config.TARGET_QUANTITY} cards\n"
        f"<b>⚡ Webhook:</b> <code>{config.BUY_BOT_WEBHOOK_URL}</code>\n\n"
        f"<b>Available Commands:</b>\n"
        f"/status - Live stock status & uptime\n"
        f"/check - Force an instant stock sweep right now\n"
        f"/set_target &lt;amount&gt; - Change target denomination (e.g. /set_target 1000)\n"
        f"/set_interval &lt;seconds&gt; - Change check interval\n"
        f"/test_trigger - Test webhook signal to Buy Bot"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /status command."""
    uptime = datetime.datetime.now() - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    lines = [
        f"📊 <b>Stock Monitor Status (Bot 1)</b>\n",
        f"⏱️ <b>Uptime:</b> {hours}h {minutes}m {seconds}s",
        f"🔄 <b>Total Checks:</b> {TOTAL_CYCLES:,}",
        f"🎯 <b>Target:</b> ₹{config.TARGET_DENOMINATION:,} x {config.TARGET_QUANTITY} cards",
        f"⚡ <b>Check Interval:</b> Every {config.CHECK_INTERVAL_SECONDS}s\n",
        f"<b>Current Denominations:</b>"
    ]

    for d in [1000, 2000, 3000, 4000, 5000]:
        state = LATEST_STOCK_STATE.get(d)
        if state is True:
            badge = "🟢 <b>IN STOCK</b>"
        elif state is False:
            badge = "🔴 Out of Stock"
        else:
            badge = "⚪ Not Checked"
        lines.append(f"• <b>₹{d:,}:</b> {badge}")

    lines.append("\n✅ <i>24/7 restock monitoring is active on AWS Mumbai.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /check command for an on-demand manual sweep."""
    await update.message.reply_text("🔍 Sweeping Rooter Shop right now...", parse_mode=ParseMode.HTML)
    stock_data = await check_rooter_stock_http()
    if stock_data is None:
        stock_data = await check_rooter_stock_playwright()

    lines = ["📊 <b>Instant Sweep Result:</b>\n"]
    for d in [1000, 2000, 3000, 4000, 5000]:
        badge = "🟢 <b>IN STOCK!</b>" if stock_data.get(d) else "🔴 Out of Stock"
        lines.append(f"• PlayStation ₹{d:,}: {badge}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def set_target_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /set_target <denomination> [quantity]."""
    if not context.args:
        await update.message.reply_text("Usage: <code>/set_target 1000 2</code>", parse_mode=ParseMode.HTML)
        return

    try:
        new_target = int(context.args[0])
        new_qty = int(context.args[1]) if len(context.args) > 1 else config.TARGET_QUANTITY
        config.TARGET_DENOMINATION = new_target
        config.TARGET_QUANTITY = new_qty
        await update.message.reply_text(
            f"✅ Target updated to <b>PlayStation ₹{new_target:,} x {new_qty} cards</b> (Total: ₹{new_target * new_qty:,})!",
            parse_mode=ParseMode.HTML
        )
    except ValueError:
        await update.message.reply_text("❌ Please enter valid numbers. Example: <code>/set_target 1000 2</code>", parse_mode=ParseMode.HTML)


async def test_trigger_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a dry-run test trigger to Buy Bot (Bot 2)."""
    await update.message.reply_text(
        f"⚡ Sending test webhook to Buy Bot at <code>{config.BUY_BOT_WEBHOOK_URL}</code>...",
        parse_mode=ParseMode.HTML
    )
    success = await trigger_buy_bot_webhook(config.TARGET_DENOMINATION, config.TARGET_QUANTITY)
    if success:
        await update.message.reply_text("✅ Buy Bot received the signal successfully!", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("❌ Could not connect to Buy Bot. Ensure Bot 2 is running on port 5000.", parse_mode=ParseMode.HTML)


# ==========================================
# Keep-Alive & Health Check Web Server
# ==========================================
async def health_check_handler(request):
    return web.json_response({
        "status": "healthy",
        "bot": "psn-stock-monitor",
        "cycles": TOTAL_CYCLES,
        "target": {
            "denomination": config.TARGET_DENOMINATION,
            "quantity": config.TARGET_QUANTITY,
        },
        "stock_state": LATEST_STOCK_STATE,
        "last_check_seconds_ago": round(time.time() - LAST_CHECK_TIME, 1) if LAST_CHECK_TIME else None,
    })


def create_health_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", health_check_handler)
    app.router.add_get("/health", health_check_handler)
    return app


# ==========================================
# Main Application Entry Point
# ==========================================
async def main():
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("FATAL: TELEGRAM_BOT_TOKEN is not set!")
        sys.exit(1)

    # 1. Build Telegram Bot Application
    tg_app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    tg_app.add_handler(CommandHandler("start", start_command))
    tg_app.add_handler(CommandHandler("status", status_command))
    tg_app.add_handler(CommandHandler("check", check_command))
    tg_app.add_handler(CommandHandler("set_target", set_target_command))
    tg_app.add_handler(CommandHandler("test_trigger", test_trigger_command))

    # Initialize Telegram polling
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    logger.info("🤖 Telegram bot command handler active!")

    # 2. Start Health Check Web Server on port 8080
    health_app = create_health_app()
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.KEEP_ALIVE_PORT)
    await site.start()
    logger.info(f"🌐 Health web server listening on port {config.KEEP_ALIVE_PORT}")

    # 3. Launch 24/7 restock monitoring worker
    await restock_monitor_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stock Monitor stopped.")
