"""
PlayStation Gift Card Stock Monitor & Telegram Alert Bot.
Designed for 24/7 autonomous execution on Replit with resource-efficient Playwright and a keep-alive web server.
"""

import sys
import os
import json
import asyncio
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

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

# Ensure UTF-8 output on Windows consoles if applicable
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


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
async def send_telegram_alert(
    platform: str,
    item_name: str,
    price: str,
    url: str,
    status: str,
) -> bool:
    """Sends a formatted instant notification to Telegram Bot."""
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram Bot Token or Chat ID is missing! Skipping alert.")
        return False

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

    api_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(api_url, json=payload)
            if resp.status_code == 200:
                logger.info(f"✅ Telegram alert sent successfully for '{item_name}' on {platform}!")
                return True
            else:
                logger.error(f"Telegram API error {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


# ==========================================
# Playwright & Scraping Utilities
# ==========================================
async def block_heavy_resources(route):
    """Aborts images, fonts, media, and stylesheets to save CPU/RAM on Replit."""
    if route.request.resource_type in ["image", "media", "font", "stylesheet"]:
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

        # Navigate to target page
        await page.goto(url, timeout=config.PAGE_TIMEOUT_MS, wait_until="domcontentloaded")

        try:
            await page.wait_for_selector(wait_sel, timeout=10000)
        except Exception:
            pass  # Page loaded enough to continue

        # Allow dynamic JS to hydrate
        await page.wait_for_timeout(2000)

        # Extract text content
        content_text = ""
        try:
            elements = page.locator(container_sel)
            count = await elements.count()
            if count > 0:
                texts = [await elements.nth(i).inner_text() for i in range(min(count, 5))]
                content_text = " ".join(texts).lower()
            else:
                content_text = (await page.inner_text("body")).lower()
        except Exception:
            content_text = (await page.inner_text("body")).lower()

        # Extract price if selector is configured
        price = ""
        if price_sel:
            try:
                price_el = page.locator(price_sel).first
                if await price_el.is_visible(timeout=2000):
                    price = (await price_el.inner_text()).strip()
            except Exception:
                price = ""

        # Determine stock status
        is_out = any(keyword in content_text for keyword in out_keywords)
        is_in = any(keyword in content_text for keyword in in_keywords)

        if is_out and not is_in:
            status = "OUT_OF_STOCK"
        elif is_in and not is_out:
            status = "IN_STOCK"
        elif is_in and is_out:
            # If both are present, inspect priority: if 'add to cart' button is active
            status = "IN_STOCK" if "add to cart" in content_text or "buy now" in content_text else "OUT_OF_STOCK"
        else:
            # Ambiguous/default check
            status = "OUT_OF_STOCK" if is_out else "UNKNOWN"

        return {
            "status": status,
            "price": price,
            "error": None,
        }

    except PlaywrightTimeoutError:
        logger.warning(f"Timeout while checking {target['platform']} ({url})")
        return {"status": "ERROR", "price": "", "error": "Timeout"}
    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with Playwright: {e}")
        return {"status": "ERROR", "price": "", "error": str(e)}
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
                return {"status": "ERROR", "price": "", "error": f"HTTP {resp.status_code}"}

            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract container text
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

            is_out = any(keyword in content_text for keyword in out_keywords)
            is_in = any(keyword in content_text for keyword in in_keywords)

            if is_out and not is_in:
                status = "OUT_OF_STOCK"
            elif is_in and not is_out:
                status = "IN_STOCK"
            elif is_in and is_out:
                status = "IN_STOCK" if "add to cart" in content_text or "in stock" in content_text else "OUT_OF_STOCK"
            else:
                status = "OUT_OF_STOCK" if is_out else "UNKNOWN"

            return {
                "status": status,
                "price": price,
                "error": None,
            }

    except Exception as e:
        logger.warning(f"Error checking {target['platform']} with HTTP requests: {e}")
        return {"status": "ERROR", "price": "", "error": str(e)}


# ==========================================
# Keep-Alive HTTP Server (for UptimeRobot on Replit)
# ==========================================
async def start_keep_alive_server():
    """Lightweight HTTP server on port 8080 for UptimeRobot to ping."""
    async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            await reader.read(512)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            body = f"OK: PlayStation Stock Monitor is active.\nTimestamp: {now}\n"
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                "Connection: close\r\n"
                "\r\n"
                + body
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
        logger.info(f"🌐 Keep-Alive server listening on http://0.0.0.0:{config.KEEP_ALIVE_PORT}")
        return server
    except Exception as e:
        logger.warning(f"Could not bind Keep-Alive server to port {config.KEEP_ALIVE_PORT}: {e}")
        return None


# ==========================================
# Main Monitoring Cycle
# ==========================================
async def run_monitor_cycle(browser: Optional[Browser], context: Optional[BrowserContext], state: Dict[str, Any]):
    """Performs one full sweep over all configured target websites."""
    logger.info("=" * 60)
    logger.info(f"🔍 Starting stock check sweep at {datetime.datetime.now().strftime('%H:%M:%S')}...")

    for target in config.TARGET_SITES:
        if not target.get("enabled", True):
            continue

        target_id = target["id"]
        platform = target["platform"]
        item_name = target["item_name"]
        url = target["url"]
        engine = target.get("engine", "playwright").lower()

        logger.info(f"Checking [{platform}] - {item_name} (via {engine})...")

        result = {}
        if engine == "playwright" and context:
            result = await check_target_playwright(context, target)
        else:
            result = await check_target_requests(target)

        current_status = result.get("status", "UNKNOWN")
        price = result.get("price", "")

        previous_data = state.get(target_id, {})
        previous_status = previous_data.get("status")

        # Status icon formatting
        icon = "🟢 IN STOCK" if current_status == "IN_STOCK" else ("🔴 OUT OF STOCK" if current_status == "OUT_OF_STOCK" else "⚠️ " + current_status)
        logger.info(f"  -> Result: {icon} | Price: {price if price else 'N/A'}")

        # Check for State Transition: OUT_OF_STOCK -> IN_STOCK
        should_alert = False
        if previous_status == "OUT_OF_STOCK" and current_status == "IN_STOCK":
            logger.info(f"🚨 Restock transition detected for {item_name} on {platform}!")
            should_alert = True
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

        # Update local state if not error
        if current_status != "ERROR":
            state[target_id] = {
                "platform": platform,
                "item_name": item_name,
                "status": current_status,
                "last_price": price,
                "last_checked": datetime.datetime.now().isoformat(),
            }
            save_state(state)

        # Gentle delay between sites to avoid rate-limiting and CPU spikes
        await asyncio.sleep(config.SITE_CHECK_DELAY_SECONDS)

    logger.info("🏁 Stock check sweep complete. Resting until next interval.")


# ==========================================
# Main Application Entry Point
# ==========================================
async def main():
    logger.info("=" * 60)
    logger.info("🚀 PlayStation Gift Card Monitor starting up...")
    logger.info(f"⏱️ Check Interval: {config.CHECK_INTERVAL_SECONDS} seconds")
    logger.info(f"📱 Telegram Alerts: {'Configured' if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID else 'NOT CONFIGURED (Check .env)'}")
    logger.info("=" * 60)

    # Start Keep-Alive Web Server for UptimeRobot
    await start_keep_alive_server()

    # Load persistent state
    state = load_state()

    # Launch Playwright Browser once with resource-saving flags for Replit
    playwright_instance = None
    browser = None
    context = None

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
        )
        logger.info("🌐 Playwright Headless Chromium successfully initialized.")
    except Exception as e:
        logger.error(f"Failed to start Playwright browser: {e}")
        logger.error("Continuing in fallback HTTP-only mode. Ensure 'playwright install chromium' is run.")

    cycle_count = 0
    try:
        while True:
            cycle_count += 1
            try:
                await run_monitor_cycle(browser, context, state)
            except Exception as e:
                logger.error(f"Unexpected error during monitor cycle #{cycle_count}: {e}", exc_info=True)

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
