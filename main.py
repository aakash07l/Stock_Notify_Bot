"""
PlayStation Gift Card Stock Monitor & Telegram Alert Bot.
Designed for 24/7 autonomous execution on Replit with resource-efficient Playwright and a keep-alive web server.
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
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

import config

# ==========================================
# Logging Configuration
# ==========================================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("PSNMonitor")

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# Global state tracking for keep-alive dashboard
LATEST_STOCK_STATE: Dict[str, Any] = {}
LAST_CHECKED_TIMES: Dict[str, float] = {}
BOT_START_TIME = datetime.datetime.now()
TOTAL_CYCLES_COMPLETED = 0


# ==========================================
# State Management (Local JSON persistence)
# ==========================================
def load_state() -> Dict[str, Any]:
    """Loads previous stock status from local JSON file."""
    state_file = Path(config.STATE_FILE_PATH)
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not read state file ({e}). Starting with fresh state.")
        return {}


def save_state(state: Dict[str, Any]):
    """Persists current stock status to local JSON file atomically."""
    temp_file = Path(f"{config.STATE_FILE_PATH}.tmp")
    state_file = Path(config.STATE_FILE_PATH)
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        temp_file.replace(state_file)
    except Exception as e:
        logger.error(f"Failed to persist state file: {e}")


# ==========================================
# Telegram Bot Dispatcher
# ==========================================
async def send_telegram_message(message_html: str) -> bool:
    """Helper to send any HTML formatted message to all configured Telegram chats (User + Ajay)."""
    if not config.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram Bot Token is missing! Skipping notification.")
        return False

    chat_ids = getattr(config, "TELEGRAM_CHAT_IDS", [])
    if not chat_ids:
        if config.TELEGRAM_CHAT_ID:
            chat_ids = [cid.strip() for cid in str(config.TELEGRAM_CHAT_ID).split(",") if cid.strip()]
        else:
            logger.warning("No Telegram Chat ID configured! Skipping notification.")
            return False

    api_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    any_success = False

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for chat_id in chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": message_html,
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
                    logger.error(f"Failed to send Telegram message to chat {chat_id}: {ce}")
    except Exception as e:
        logger.error(f"Telegram client error: {e}")
        return False

    return any_success



async def send_startup_notification(engine_info: str = "🟢 Playwright Chromium Headless") -> bool:
    """Sends an instant confirmation message to Telegram when the bot boots up."""
    if not config.SEND_STARTUP_MESSAGE:
        return False

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

    platforms_list = ", ".join([s["platform"] for s in config.TARGET_SITES if s.get("enabled", True)])

    msg = (
        f"🤖 <b>PlayStation Stock Monitor Started!</b>\n\n"
        f"📡 <b>Status:</b> 🟢 <b>Online & Running 24/7 (Railway/Cloud)</b>\n"
        f"🌐 <b>Engine:</b> {engine_info}\n"
        f"⏱️ <b>Check Interval:</b> Every {config.CHECK_INTERVAL_SECONDS // 60} minutes\n"
        f"🎯 <b>Tracking Platforms:</b> {platforms_list}\n"
        f"⏰ <b>Started At:</b> {formatted_time}\n\n"
        f"🔄 <i>Running initial sweep now... You will receive a summary shortly!</i>"
    )
    logger.info("📤 Sending startup handshake notification to Telegram...")
    return await send_telegram_message(msg)


async def send_initial_summary_report(results: List[Dict[str, Any]]) -> bool:
    """Sends a complete stock overview report after the first cycle completes."""
    if not config.SEND_INITIAL_SUMMARY:
        return False

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    lines = [
        f"📊 <b>Initial Stock Sweep Completed!</b>",
        f"⏰ <b>Time:</b> {formatted_time}\n",
    ]

    for item in results:
        status = item.get("status", "UNKNOWN")
        badge = "🟢 In Stock" if status == "IN_STOCK" else ("🔴 Out of Stock" if status == "OUT_OF_STOCK" else f"⚠️ {status}")
        price_str = f" ({item.get('price')})" if item.get("price") else ""
        lines.append(f"• <b>{item.get('platform')}:</b> {badge}{price_str}")

    lines.append("\n🔔 <i>Continuous restock monitoring active! You will get instant alerts the moment any card restocks.</i>")
    return await send_telegram_message("\n".join(lines))


async def send_periodic_summary_report(results: List[Dict[str, Any]], cycle_num: int) -> bool:
    """Sends a periodic live stock table update (e.g. every 2 hours)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    lines = [
        f"📊 <b>Periodic Stock Check Update (Cycle #{cycle_num})</b>",
        f"⏰ <b>Time:</b> {formatted_time}\n",
    ]

    for item in results:
        status = item.get("status", "UNKNOWN")
        badge = "🟢 In Stock" if status == "IN_STOCK" else ("🔴 Out of Stock" if status == "OUT_OF_STOCK" else f"⚠️ {status}")
        price_str = f" ({item.get('price')})" if item.get("price") else ""
        lines.append(f"• <b>{item.get('platform')}:</b> {badge}{price_str}")

    lines.append("\n✅ <i>Bot is active 24/7. Instant restock alert will trigger the moment a card restocks!</i>")
    return await send_telegram_message("\n".join(lines))


async def send_heartbeat_notification(cycle_num: int) -> bool:
    """Periodic health check notification (e.g. every 6 hours)."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M %p IST")

    msg = (
        f"💓 <b>Stock Monitor Heartbeat</b>\n\n"
        f"✅ Bot is running smoothly 24/7 in cloud.\n"
        f"🔄 <b>Cycles Completed:</b> {cycle_num}\n"
        f"⏰ <b>Timestamp:</b> {formatted_time}\n"
        f"🎯 Monitoring all {len(config.TARGET_SITES)} platforms 24/7."
    )
    return await send_telegram_message(msg)


async def send_telegram_alert(
    platform: str,
    item_name: str,
    price: str,
    url: str,
    status: str,
) -> bool:
    """Sends a formatted restock notification to Telegram Bot."""
    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

    message_text = (
        f"🚨 <b>RESTOCK ALERT: PlayStation Gift Card!</b>\n\n"
        f"🎮 <b>Platform:</b> {platform}\n"
        f"💳 <b>Item:</b> {item_name}\n"
        f"💰 <b>Price:</b> {price if price else 'Check Site'}\n"
        f"📦 <b>Status:</b> 🟢 <b>IN STOCK NOW!</b>\n"
        f"⏰ <b>Detected At:</b> {formatted_time}\n\n"
        f"👉 <a href='{url}'><b>CLICK HERE TO BUY NOW</b></a>\n"
    )

    logger.info(f"🚨 Dispatched Restock Alert for {item_name} on {platform}!")
    return await send_telegram_message(message_text)


# ==========================================
# Playwright & Scraping Utilities
# ==========================================
async def block_heavy_resources(route):
    """Aborts images, fonts, and media to save CPU/RAM while keeping stylesheets for Cloudflare compatibility."""
    if route.request.resource_type in ["image", "media", "font"]:
        await route.abort()
    else:
        await route.continue_()


async def check_target_playwright(context: BrowserContext, target: Dict[str, Any]) -> Dict[str, Any]:
    """Inspects a JavaScript-heavy SPA website using Playwright."""
    url = target["url"]
    wait_sel = target.get("wait_selector") or "body"
    out_keywords = [k.lower() for k in target.get("out_of_stock_keywords", [])]
    in_keywords = [k.lower() for k in target.get("in_stock_keywords", [])]
    container_sel = target.get("container_selector") or "body"
    price_sel = target.get("price_selector", "")

    page: Optional[Page] = None
    try:
        page = await context.new_page()

        if config.BLOCK_MEDIA_RESOURCES:
            await page.route("**/*", block_heavy_resources)

        try:
            # wait_until="commit" returns as soon as HTTP response begins, avoiding getting stuck on third-party tracking scripts
            await page.goto(url, timeout=config.PAGE_TIMEOUT_MS, wait_until="commit")
            await page.wait_for_timeout(3500)
        except Exception as e:
            logger.warning(f"Navigation note for {target['platform']}: {e}")

        # Extract comprehensive text content from the page
        content_text = ""
        try:
            content_text = (await page.inner_text("body")).lower()
        except Exception:
            try:
                content_text = (await page.content()).lower()
            except Exception:
                content_text = ""

        # Extract price if selector is configured
        price = ""
        if price_sel:
            try:
                price_el = page.locator(price_sel).first
                if await price_el.is_visible(timeout=2000):
                    price = (await price_el.inner_text()).strip()
            except Exception:
                price = ""

        # Comprehensive buy keywords covering regular e-commerce and Rooter/gaming stores
        buy_keywords = [
            "add to cart", "in stock", "buy now", "proceed to pay",
            "pay via wallet", "pay with wallet", "pay ₹", "pay rs",
            "get voucher", "pre order"
        ]

        # 1. Check for visible active (non-disabled) checkout/buy buttons on the page
        active_buy_btn_found = False
        buy_button_selectors = (
            "button[data-testid='proceed-to-pay'], button[testid='proceed-to-pay'], "
            "button[data-testid='add-address-btn'], button[testid='add-address-btn'], "
            "button:has-text('Proceed to Pay'), button:has-text('Pay via wallet'), "
            "button:has-text('Pay ₹'), button:has-text('Pay Rs'), "
            "button:has-text('Add to Cart'), button:has-text('Buy Now'), "
            "a:has-text('Add to Cart'), a:has-text('Buy Now')"
        )
        try:
            buy_btns = page.locator(buy_button_selectors)
            btn_count = await buy_btns.count()
            for idx in range(min(btn_count, 5)):
                btn = buy_btns.nth(idx)
                if await btn.is_visible(timeout=500):
                    btn_text = (await btn.inner_text()).lower()
                    if "out of stock" not in btn_text and "sold out" not in btn_text:
                        active_buy_btn_found = True
                        logger.info(f"🟢 Active buy button found for {target['platform']}: '{btn_text.strip()}'")
                        break
        except Exception:
            pass

        # 2. Check for Rooter Shop (shop.rooter.gg)
        rooter_in_stock = False
        if "rooter.gg" in url:
            active_buy_btn_found = False  # Never trust generic locator for Rooter
            rooter_action_btn = page.locator("button[data-testid='proceed-to-pay'], button[testid='proceed-to-pay']").first
            btn_text = ""
            try:
                if await rooter_action_btn.is_visible(timeout=3000):
                    btn_text = (await rooter_action_btn.inner_text()).strip().lower()
            except Exception:
                pass

            if "out of stock" in btn_text or "sold out" in btn_text:
                logger.info("🔴 Rooter main button explicitly displays 'Out of Stock'")
                is_out = True
                is_in = False
                rooter_in_stock = False
            else:
                try:
                    raw_html = (await page.content()).replace('\\"', '"')
                    # Look for all wallet code denominations and their outOfStock flags
                    denominations = re.findall(r'"name"\s*:\s*"[^"]*Wallet Code".*?"outOfStock"\s*:\s*(true|false)', raw_html)
                    has_in_stock_denom = any(d == "false" for d in denominations)
                    if has_in_stock_denom and any(k in btn_text for k in ["proceed to pay", "pay ₹", "pay rs", "add address"]):
                        rooter_in_stock = True
                        is_in = True
                        is_out = False
                        logger.info("🟢 Rooter denomination in stock and checkout button active!")
                    else:
                        is_out = True
                        is_in = False
                        rooter_in_stock = False
                        logger.info("🔴 Rooter Next.js data confirms all denominations are out of stock.")
                except Exception:
                    is_out = True
                    is_in = False
                    rooter_in_stock = False

        # 3. Check for Games The Shop live filter button "In Stock Only (N)"
        is_out = None
        is_in = None

        if "gamestheshop.com" in url:
            # GTS catalog search cards always have a dummy "Add to Cart" (+) button, even when out of stock.
            # Never trust generic buy buttons for GTS!
            active_buy_btn_found = False
            gts_matched = False

            try:
                gts_stock_btn = page.locator("button:has-text('In Stock Only')").first
                if await gts_stock_btn.is_visible(timeout=3000):
                    btn_text = await gts_stock_btn.inner_text()
                    count_match = re.search(r'\(.*?(\d+).*?\)', btn_text)
                    if count_match:
                        in_stock_count = int(count_match.group(1))
                        gts_matched = True
                        if in_stock_count == 0:
                            logger.info(f"🔴 Games The Shop filter confirms 0 items in stock ({btn_text.strip()})")
                            is_out = True
                            is_in = False
                        else:
                            logger.info(f"🟢 Games The Shop filter confirms {in_stock_count} items in stock!")
                            is_in = True
                            is_out = False
            except Exception:
                pass

            # Fallback for GTS: check raw page HTML for 'In Stock Only (N)' with optional comments
            if not gts_matched:
                try:
                    raw_html = await page.content()
                    m = re.search(r'In Stock Only[^\(]*\([^\d]*(\d+)', raw_html, re.IGNORECASE)
                    if m:
                        in_stock_count = int(m.group(1))
                        if in_stock_count == 0:
                            logger.info(f"🔴 Games The Shop HTML confirms 0 items in stock ({m.group(0)})")
                            is_out = True
                            is_in = False
                        else:
                            logger.info(f"🟢 Games The Shop HTML confirms {in_stock_count} items in stock!")
                            is_in = True
                            is_out = False
                    else:
                        # If GTS search returns 0 in-stock filter, default to OUT_OF_STOCK
                        is_out = True
                        is_in = False
                except Exception:
                    is_out = True
                    is_in = False

        # 4. Check for StanShop (stanshop.co)
        if "stanshop.co" in url:
            try:
                sold_out_count = content_text.count("sold out")
                coupon_count = content_text.count("coupon worth")
                if coupon_count > 0 and sold_out_count >= coupon_count:
                    logger.info(f"🔴 StanShop all {coupon_count} denominations are sold out ({sold_out_count} sold out tags).")
                    is_out = True
                    is_in = False
                    active_buy_btn_found = False
                elif coupon_count > 0 and sold_out_count < coupon_count:
                    logger.info(f"🟢 StanShop has stock! {coupon_count - sold_out_count} item(s) available.")
                    is_in = True
                    is_out = False
            except Exception:
                pass

        # 5. Check for Blinkit (blinkit.com - Mumbai location)
        if "blinkit.com" in url:
            active_buy_btn_found = False
            try:
                detect_btn = page.locator("button:has-text('Detect my location')").first
                if await detect_btn.is_visible(timeout=1500):
                    await detect_btn.click()
                    await page.wait_for_timeout(2500)
                    content_text = (await page.inner_text("body")).lower()
            except Exception:
                pass

            if "playstation instant voucher" in content_text:
                idx = content_text.find("playstation instant voucher")
                surrounding = content_text[max(0, idx-100):min(len(content_text), idx+150)]
                if "out of stock" in surrounding or "currently unavailable" in surrounding:
                    is_out = True
                    is_in = False
                elif "add" in surrounding:
                    is_in = True
                    is_out = False
                else:
                    is_out = True
                    is_in = False
            else:
                is_out = True
                is_in = False

        # 6. Check for Flipkart (flipkart.com - anti-captcha safe)
        if "flipkart.com" in url:
            active_buy_btn_found = False
            try:
                cards = await page.locator("div._75nlfW, div[data-id]").all()
                psn_found = 0
                in_stock_count = 0
                for c in cards:
                    txt = (await c.inner_text()).lower()
                    if "playstation" in txt and ("gift card" in txt or "voucher" in txt or "inr" in txt):
                        psn_found += 1
                        if "currently unavailable" in txt or "coming soon" in txt or "out of stock" in txt:
                            pass
                        else:
                            in_stock_count += 1
                if psn_found > 0 and in_stock_count > 0:
                    is_in = True
                    is_out = False
                else:
                    is_out = True
                    is_in = False
            except Exception:
                is_out = True
                is_in = False

        # Determine stock status
        if is_out is None and is_in is None:
            is_out = any(keyword in content_text for keyword in out_keywords)
            is_in = any(keyword in content_text for keyword in in_keywords)
        elif is_out is None:
            is_out = any(keyword in content_text for keyword in out_keywords)
        elif is_in is None:
            is_in = any(keyword in content_text for keyword in in_keywords)

        # STRICT STOCK STATUS: is_out ALWAYS takes precedence over generic buttons
        if "gamestheshop.com" in url:
            # Games The Shop MUST be strictly OUT_OF_STOCK unless in_stock_count > 0 was verified!
            if is_in is True and is_out is False:
                status = "IN_STOCK"
            else:
                status = "OUT_OF_STOCK"
        elif "blinkit.com" in url:
            if is_in is True and is_out is False:
                status = "IN_STOCK"
            else:
                status = "OUT_OF_STOCK"
        elif "flipkart.com" in url:
            if is_in is True and is_out is False:
                status = "IN_STOCK"
            else:
                status = "OUT_OF_STOCK"
        elif is_out:
            status = "OUT_OF_STOCK"
        elif rooter_in_stock:
            status = "IN_STOCK"
        elif active_buy_btn_found:
            status = "IN_STOCK"
        elif is_in and not is_out:
            status = "IN_STOCK"
        else:
            status = "OUT_OF_STOCK"

        return {
            "platform": target["platform"],
            "item_name": target["item_name"],
            "status": status,
            "price": price,
            "url": url,
            "error": None,
        }

    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with Playwright: {e}")
        return {"platform": target["platform"], "item_name": target["item_name"], "status": "OUT_OF_STOCK", "price": "", "url": url, "error": str(e)}
    finally:
        if page:
            await page.close()


async def check_target_requests(target: Dict[str, Any]) -> Dict[str, Any]:
    """Inspects a website using lightweight HTTP requests and BeautifulSoup."""
    url = target["url"]
    out_keywords = [k.lower() for k in target.get("out_of_stock_keywords", [])]
    in_keywords = [k.lower() for k in target.get("in_stock_keywords", [])]
    container_sel = target.get("container_selector") or "body"
    price_sel = target.get("price_selector", "")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {"platform": target["platform"], "item_name": target["item_name"], "status": "OUT_OF_STOCK", "price": "", "url": url, "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")

            container_el = soup.select(container_sel) if container_sel else []
            if container_el:
                content_text = " ".join([el.get_text() for el in container_el]).lower()
            else:
                content_text = soup.get_text().lower()

            price = ""
            if price_sel:
                price_match = soup.select_one(price_sel)
                if price_match:
                    price = price_match.get_text().strip()

            buy_keywords = [
                "add to cart", "buy now", "proceed to pay",
                "pay via wallet", "pay with wallet", "pay ₹", "pay rs",
                "get voucher", "pre order"
            ]

            rooter_in_stock = False
            if "rooter.gg" in url:
                try:
                    clean_text = resp.text.replace('\\"', '"')
                    denominations = re.findall(r'"name"\s*:\s*"[^"]*Wallet Code".*?"outOfStock"\s*:\s*(true|false)', clean_text)
                    has_in_stock_denom = any(d == "false" for d in denominations)
                    if has_in_stock_denom:
                        rooter_in_stock = True
                        is_in = True
                        is_out = False
                    else:
                        rooter_in_stock = False
                        is_out = True
                        is_in = False
                except Exception:
                    is_out = True
                    is_in = False

            is_out = any(keyword in content_text for keyword in out_keywords)
            is_in = any(keyword in content_text for keyword in in_keywords)

            if "gamestheshop.com" in url:
                count_match = re.search(r'In Stock Only[^\(]*\([^\d]*(\d+)', resp.text, re.IGNORECASE)
                if count_match:
                    if int(count_match.group(1)) == 0:
                        is_out = True
                        is_in = False
                    else:
                        is_in = True
                        is_out = False
                else:
                    is_out = True
                    is_in = False

            if "stanshop.co" in url:
                sold_out_count = content_text.count("sold out")
                coupon_count = content_text.count("coupon worth")
                if coupon_count > 0 and sold_out_count >= coupon_count:
                    is_out = True
                    is_in = False
                elif coupon_count > 0 and sold_out_count < coupon_count:
                    is_in = True
                    is_out = False

            if "gamestheshop.com" in url:
                if is_in is True and is_out is False:
                    status = "IN_STOCK"
                else:
                    status = "OUT_OF_STOCK"
            elif is_out:
                status = "OUT_OF_STOCK"
            elif rooter_in_stock:
                status = "IN_STOCK"
            elif is_in and not is_out:
                status = "IN_STOCK"
            else:
                status = "OUT_OF_STOCK"



            return {
                "platform": target["platform"],
                "item_name": target["item_name"],
                "status": status,
                "price": price,
                "url": url,
                "error": None,
            }

    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with HTTP requests: {e}")
        return {"platform": target["platform"], "item_name": target["item_name"], "status": "ERROR", "price": "", "url": url, "error": str(e)}


# ==========================================
# Keep-Alive HTTP Server & Live Dashboard (for UptimeRobot)
# ==========================================
async def start_keep_alive_server():
    """Serves a modern live status dashboard on port 8080 for UptimeRobot to ping."""
    async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await reader.read(1024)
            uptime_seconds = int((datetime.datetime.now() - BOT_START_TIME).total_seconds())
            hours, remainder = divmod(uptime_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m {seconds}s"

            now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
            formatted_time = now_ist.strftime("%d-%b-%Y %I:%M:%S %p IST")

            # Build HTML rows for live state
            rows_html = ""
            for item_id, item_data in LATEST_STOCK_STATE.items():
                status = item_data.get("status", "PENDING")
                badge_class = "badge-in" if status == "IN_STOCK" else ("badge-out" if status == "OUT_OF_STOCK" else "badge-warn")
                badge_text = "IN STOCK" if status == "IN_STOCK" else ("OUT OF STOCK" if status == "OUT_OF_STOCK" else status)
                rows_html += f"""
                <tr>
                    <td><strong>{item_data.get('platform', '')}</strong></td>
                    <td>{item_data.get('item_name', '')}</td>
                    <td><span class="badge {badge_class}">{badge_text}</span></td>
                    <td>{item_data.get('last_price', 'N/A')}</td>
                    <td><a href="{item_data.get('url', '#')}" target="_blank" class="buy-link">Open Store ↗</a></td>
                </tr>
                """

            html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PSN Gift Card Stock Monitor</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        .card {{ max-width: 800px; margin: 0 auto; background: #1e293b; border-radius: 12px; padding: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
        h1 {{ font-size: 24px; margin-top: 0; display: flex; align-items: center; gap: 10px; }}
        .pulse {{ display: inline-block; width: 12px; height: 12px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 10px #22c55e; }}
        .stats {{ display: flex; gap: 16px; margin-bottom: 24px; font-size: 14px; color: #94a3b8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; color: #cbd5e1; font-weight: 600; }}
        .badge {{ padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: bold; }}
        .badge-in {{ background: #15803d; color: #dcfce7; }}
        .badge-out {{ background: #991b1b; color: #fee2e2; }}
        .badge-warn {{ background: #854d0e; color: #fef9c3; }}
        .buy-link {{ color: #38bdf8; text-decoration: none; font-weight: 500; }}
        .buy-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="card">
        <h1><span class="pulse"></span> PlayStation Stock Monitor (24/7 Active)</h1>
        <div class="stats">
            <div>⏱️ <strong>Uptime:</strong> {uptime_str}</div>
            <div>🔄 <strong>Cycles:</strong> {TOTAL_CYCLES_COMPLETED}</div>
            <div>⏰ <strong>Last Checked:</strong> {formatted_time}</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Platform</th>
                    <th>Item</th>
                    <th>Status</th>
                    <th>Price</th>
                    <th>Store Link</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="5" style="text-align:center; padding:20px; color:#94a3b8;">Initial sweep in progress... Refresh in a few seconds.</td></tr>'}
            </tbody>
        </table>
    </div>
</body>
</html>"""

            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(html_content.encode('utf-8'))}\r\n"
                "Connection: close\r\n"
                "\r\n"
                + html_content
            )
            writer.write(response.encode("utf-8"))
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    try:
        server = await asyncio.start_server(handle_request, "0.0.0.0", config.KEEP_ALIVE_PORT)
        logger.info(f"🌐 Keep-Alive dashboard server listening on http://0.0.0.0:{config.KEEP_ALIVE_PORT}")
        return server
    except Exception as e:
        logger.warning(f"Could not bind Keep-Alive server to port {config.KEEP_ALIVE_PORT}: {e}")
        return None


# ==========================================
# Main Monitoring Cycle
# ==========================================
async def run_monitor_cycle(browser: Optional[Browser], context: Optional[BrowserContext], state: Dict[str, Any], is_first_cycle: bool):
    """Performs one full sweep over all configured target websites."""
    global TOTAL_CYCLES_COMPLETED, LATEST_STOCK_STATE
    TOTAL_CYCLES_COMPLETED += 1

    logger.info("=" * 60)
    logger.info(f"🔍 Starting stock check sweep #{TOTAL_CYCLES_COMPLETED} at {datetime.datetime.now().strftime('%H:%M:%S')}...")

    cycle_results: List[Dict[str, Any]] = []

    for target in config.TARGET_SITES:
        if not target.get("enabled", True):
            continue

        target_id = target["id"]
        platform = target["platform"]
        item_name = target["item_name"]
        url = target["url"]
        engine = target.get("engine", "playwright").lower()

        # Check per-target throttling (e.g. Flipkart cooldown to avoid captchas)
        min_interval = target.get("min_interval_seconds", 0)
        now_ts = time.time()
        last_chk = LAST_CHECKED_TIMES.get(target_id, 0)

        if not is_first_cycle and min_interval > 0 and (now_ts - last_chk) < min_interval:
            prev_info = state.get(target_id, {})
            current_status = prev_info.get("status", "OUT_OF_STOCK")
            price = prev_info.get("last_price", "")
            cooldown_left = int(min_interval - (now_ts - last_chk))
            logger.info(f"⏳ [{platform}] Cooldown active ({cooldown_left}s remaining to prevent captcha). Reusing status: {current_status}")
            cycle_results.append({
                "platform": platform,
                "item_name": item_name,
                "status": current_status,
                "price": price,
                "url": url,
            })
            continue

        LAST_CHECKED_TIMES[target_id] = now_ts

        logger.info(f"Checking [{platform}] - {item_name} (via {engine})...")

        result = {}
        if engine == "playwright" and context:
            result = await check_target_playwright(context, target)
        else:
            result = await check_target_requests(target)

        current_status = result.get("status", "UNKNOWN")
        price = result.get("price", "")
        cycle_results.append(result)

        previous_data = state.get(target_id, {})
        previous_status = previous_data.get("status")

        icon = "🟢 IN STOCK" if current_status == "IN_STOCK" else ("🔴 OUT OF STOCK" if current_status == "OUT_OF_STOCK" else "⚠️ " + current_status)
        logger.info(f"  -> Result: {icon} | Price: {price if price else 'N/A'}")

        # Update global state for web dashboard
        LATEST_STOCK_STATE[target_id] = {
            "platform": platform,
            "item_name": item_name,
            "status": current_status,
            "last_price": price,
            "url": url,
            "last_checked": datetime.datetime.now().isoformat(),
        }

        # Check for Alert Triggers
        should_alert = False

        # Condition 1: Out of Stock -> In Stock transition
        if previous_status == "OUT_OF_STOCK" and current_status == "IN_STOCK":
            logger.info(f"🚨 Restock transition detected for {item_name} on {platform}!")
            should_alert = True
        # Condition 2: Initial Run In-Stock alert (if enabled)
        elif previous_status is None and current_status == "IN_STOCK" and config.NOTIFY_ON_INITIAL_RUN:
            logger.info(f"📢 Initial In-Stock detected for {item_name} on {platform}!")
            should_alert = True

        if should_alert:
            await send_telegram_alert(
                platform=platform,
                item_name=item_name,
                price=price,
                url=url,
                status=current_status,
            )

        # Update persistent local state
        if current_status != "ERROR":
            state[target_id] = {
                "platform": platform,
                "item_name": item_name,
                "status": current_status,
                "last_price": price,
                "last_checked": datetime.datetime.now().isoformat(),
            }
            save_state(state)

        # Gentle delay between sites
        await asyncio.sleep(config.SITE_CHECK_DELAY_SECONDS)

    # If first cycle, dispatch summary report to Telegram so user has 100% visibility
    if is_first_cycle:
        logger.info("📤 Sending initial summary overview to Telegram...")
        await send_initial_summary_report(cycle_results)
    elif config.PERIODIC_SUMMARY_CYCLES > 0 and TOTAL_CYCLES_COMPLETED % config.PERIODIC_SUMMARY_CYCLES == 0:
        logger.info(f"📤 Sending periodic stock update (Cycle #{TOTAL_CYCLES_COMPLETED}) to Telegram...")
        await send_periodic_summary_report(cycle_results, TOTAL_CYCLES_COMPLETED)

    # Periodic heartbeat notification (once every 24 hours)
    if config.HEARTBEAT_CYCLE_INTERVAL > 0 and TOTAL_CYCLES_COMPLETED % config.HEARTBEAT_CYCLE_INTERVAL == 0:
        if config.PERIODIC_SUMMARY_CYCLES > 0 and TOTAL_CYCLES_COMPLETED % config.PERIODIC_SUMMARY_CYCLES == 0:
            await asyncio.sleep(2)
        logger.info("📤 Sending periodic heartbeat to Telegram...")
        await send_heartbeat_notification(TOTAL_CYCLES_COMPLETED)


    logger.info("🏁 Stock check sweep complete. Resting until next interval.")


# ==========================================
# Main Application Entry Point
# ==========================================
async def main():
    logger.info("=" * 60)
    logger.info("🚀 PlayStation Gift Card Monitor starting up...")
    logger.info(f"⏱️ Check Interval: {config.CHECK_INTERVAL_SECONDS} seconds")
    logger.info(f"📱 Telegram Alerts: {'Configured' if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID else 'NOT CONFIGURED'}")
    logger.info("=" * 60)

    # Start Keep-Alive Web Server for UptimeRobot
    await start_keep_alive_server()

    state = load_state()

    playwright_instance = None
    browser = None
    context = None
    engine_info = "🟢 Playwright Chromium Headless"

    try:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-zygote",
                "--single-process",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-extensions",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            geolocation={"latitude": 19.0760, "longitude": 72.8777},
            permissions=["geolocation"],
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )
        logger.info("🌐 Playwright Headless Chromium successfully initialized.")
    except Exception as e:
        logger.error(f"Failed to start Playwright browser: {e}")
        engine_info = f"⚠️ Fallback HTTP (Playwright Error: {e})"
        logger.error("Continuing in fallback HTTP-only mode.")

    # Dispatch Startup Handshake to Telegram with verified engine info
    await send_startup_notification(engine_info=engine_info)

    is_first = True
    try:
        while True:
            try:
                await run_monitor_cycle(browser, context, state, is_first_cycle=is_first)
                is_first = False
            except Exception as e:
                logger.error(f"Unexpected error during monitor cycle #{TOTAL_CYCLES_COMPLETED}: {e}", exc_info=True)

            logger.info(f"💤 Sleeping for {config.CHECK_INTERVAL_SECONDS}s before next check...\n")
            await asyncio.sleep(config.CHECK_INTERVAL_SECONDS)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("🛑 Shutting down PlayStation Stock Monitor...")
    finally:
        if context:
            await context.close()
        if browser:
            await browser.close()
        if playwright_instance:
            await playwright_instance.stop()
        logger.info("👋 Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
