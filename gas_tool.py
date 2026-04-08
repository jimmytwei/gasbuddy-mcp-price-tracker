import asyncio
import random
import re
from typing import Dict, List

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
    Optimized for memory and address accuracy.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Block images, trackers, CSS, and Fonts
        resource_regex = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|ico|css|woff|woff2)|google-analytics|doubleclick")
        await page.route(resource_regex, lambda r: r.abort())

        fuel_id = FUEL_MAP.get(fuel_type.lower(), "1")
        safe_location = location.replace(",", "%2C").replace(" ", "%20")
        url = f"https://www.gasbuddy.com/home?search={safe_location}&fuel={fuel_id}&method=all&maxAge=0"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            await asyncio.sleep(random.uniform(2, 3))
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.5)

            # Target the station containers
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
                        
                        # Address filtering
                        address = "Unknown Address"
                        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                        
                        for line in lines:
                            # Skip common non-address "noise" lines
                            exclude_terms = ["AGO", "HOURS", "MIN", "SEC", "UPDATED", "REPORTED"]
                            if any(term in line.upper() for term in exclude_terms):
                                continue
                            
                            # Skip the station name itself
                            if line.lower() == name.lower():
                                continue
                            
                            # Matches lines starting with numbers (e.g., '222 Jibboom St')
                            if re.search(r'^\d+\s+[A-Za-z0-9]', line):
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
    import sys
    loc = sys.argv[1] if len(sys.argv) > 1 else input("Enter Location: ")
    
    print(f"Fetching prices for {loc}...")
    results = asyncio.run(get_cheapest_gas(loc))
    
    if not results:
        print("No results found. Verify your location or check for site layout changes.")
    else:
        for i, r in enumerate(results, 1):
            tag = " (CASH)" if r['is_cash'] else ""
            print(f"{i}. ${r['price']:.2f}{tag} - {r['station']} @ {r['address']}")
