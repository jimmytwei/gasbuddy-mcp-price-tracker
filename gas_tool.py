import asyncio
import random
import re
import string
import sys
from typing import Dict, List
from urllib.parse import quote_plus

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

FUEL_MAP = {
    "regular": "1",
    "midgrade": "2",
    "premium": "3",
    "diesel": "4",
    "unl88": "11",
    "e85": "12"
}


async def get_cheapest_gas(location: str, fuel_type: str = "regular") -> List[dict]:
    """
    Scrapes GasBuddy using "Fuzzy Selectors" to handle layout changes.
    Returns the unique stations found.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Standardize User Agent string length
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Performance: Block images, trackers, CSS, and Fonts
        resource_regex = re.compile(
            r"\.(png|jpg|jpeg|gif|webp|svg|ico|css|woff|woff2)|"
            r"google-analytics|doubleclick"
        )
        await page.route(resource_regex, lambda r: r.abort())

        fuel_id = FUEL_MAP.get(fuel_type.lower(), "1")
        safe_location = quote_plus(location)
        url = (
            f"https://www.gasbuddy.com/home?search={safe_location}"
            f"&fuel={fuel_id}&method=all&maxAge=0"
        )

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            await asyncio.sleep(random.uniform(2, 3))
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.5)

            # FUZZY selector: Find div containers with price and heading
            station_cards = await page.locator('div:has(h3):has-text("$")').all()
            gas_results: Dict[str, dict] = {}

            for card in station_cards:
                full_text = await card.inner_text()
                if len(full_text) > 1000:
                    continue

                if "$" in full_text:
                    try:
                        # Fuzzy name selection
                        name_el = card.locator('h3, h2, [class*="name"]').first
                        if await name_el.count() > 0:
                            name = (await name_el.inner_text()).strip()
                        else:
                            name = "Unknown"

                        # Price extraction
                        price_match = re.search(r'\$(\d+\.\d+)', full_text)
                        if not price_match:
                            continue

                        # Address extraction logic
                        address = "Unknown Address"

                        # Primary: Try targeting specific address elements
                        addr_el = card.locator(
                            '[class*="address"], [class*="Address"]'
                        ).first
                        if await addr_el.count() > 0:
                            address = (await addr_el.inner_text()).strip()
                        else:
                            # Fallback: Fuzzy line matching
                            lines = [
                                l.strip() for l in full_text.split('\n')
                                if l.strip()
                            ]
                            exclude = [
                                "AGO", "HOURS", "MIN", "SEC", "UPDATED",
                                "REPORTED", "OWNER", "USER", "LOG IN"
                            ]

                            for line in lines:
                                line_upper = line.upper()
                                if any(term in line_upper for term in exclude):
                                    continue

                                # Don't use the price or name as the address
                                if "$" in line or name.lower() in line.lower():
                                    continue

                                # Fuzzy Address: Digits + Space + Letters
                                if re.search(r'\d+\s+[A-Za-z]+', line):
                                    address = line
                                    break

                        # Remove newline and everything after it
                        if '\n' in address:
                            address = address.split('\n')[0].strip()

                        if address not in gas_results:
                            gas_results[address] = {
                                "station": name,
                                "price": float(price_match.group(1)),
                                "address": string.capwords(address),
                                "is_cash": "CASH" in full_text.upper()
                            }
                    except Exception:
                        continue

            return sorted(gas_results.values(), key=lambda x: x['price'])

        except Exception as e:
            print(f"Scraper Error: {e}")
            return []
        finally:
            await browser.close()


if __name__ == "__main__":
    loc_val = sys.argv[1] if len(sys.argv) > 1 else input("Enter Location: ")
    print(f"Searching for gas in {loc_val}...")
    results = asyncio.run(get_cheapest_gas(loc_val))

    if not results:
        print("No results found. Check if the site structure has changed.")
    else:
        for i, r in enumerate(results, 1):
            tag = " (CASH)" if r['is_cash'] else ""
            print(
                f"{i}. ${r['price']:.2f}{tag} - "
                f"{r['station']} @ {r['address']}"
            )