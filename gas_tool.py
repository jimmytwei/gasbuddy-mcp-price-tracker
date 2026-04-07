import asyncio
import random
import re
import time
from typing import Dict, List, Optional

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
    Scrapes GasBuddy and RETURNS a list of the top 3 unique stations.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Block heavy assets for speed
        await page.route(re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|ico)|google-analytics|doubleclick"), lambda r: r.abort())

        fuel_id = FUEL_MAP.get(fuel_type.lower(), "1")
        safe_location = location.replace(",", "%2C").replace(" ", "%20")
        url = f"https://www.gasbuddy.com/home?search={safe_location}&fuel={fuel_id}&method=all&maxAge=0"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(2, 3))
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.5)

            station_cards = await page.locator('div[class*="StationDisplay-module__container"], [class*="station"]').all()
            gas_results: Dict[str, dict] = {}

            for card in station_cards:
                full_text = await card.inner_text()
                if "$" in full_text:
                    try:
                        name_el = card.locator('h3').first
                        name = (await name_el.inner_text()).strip() if await name_el.count() > 0 else "Unknown"
                        
                        price_match = re.search(r'\$(\d+\.\d+)', full_text)
                        if not price_match: continue
                        
                        address = "Unknown Address"
                        for line in [l.strip() for l in full_text.split('\n') if l.strip()]:
                            if re.search(r'\d+\s+[A-Za-z]', line):
                                address = line
                                break

                        if address not in gas_results:
                            gas_results[address] = {
                                "station": name,
                                "price": float(price_match.group(1)),
                                "address": address,
                                "is_cash": "CASH" in full_text.upper()
                            }
                    except: continue

            final_list = sorted(gas_results.values(), key=lambda x: x['price'])
            return final_list[:3]

        except Exception as e:
            print(f"Scraper Error: {e}")
            return []
        finally:
            await browser.close()

if __name__ == "__main__":
    # Standalone CLI mode
    loc = input("Enter Location: ")
    results = asyncio.run(get_cheapest_gas(loc))
    for i, r in enumerate(results, 1):
        tag = " (CASH)" if r['is_cash'] else ""
        print(f"{i}. ${r['price']}{tag} - {r['station']} @ {r['address']}")
