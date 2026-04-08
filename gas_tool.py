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
    Scrapes GasBuddy using "Fuzzy Selectors" to handle layout changes.
    Returns the top 3 unique stations.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        # Performance: Block images, trackers, CSS, and Fonts
        resource_regex = re.compile(r"\.(png|jpg|jpeg|gif|webp|svg|ico|css|woff|woff2)|google-analytics|doubleclick")
        await page.route(resource_regex, lambda r: r.abort())

        fuel_id = FUEL_MAP.get(fuel_type.lower(), "1")
        safe_location = location.replace(",", "%2C").replace(" ", "%20")
        url = f"https://www.gasbuddy.com/home?search={safe_location}&fuel={fuel_id}&method=all&maxAge=0"

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Anti-bot logic
            await asyncio.sleep(random.uniform(2, 3))
            await page.mouse.wheel(0, 2000)
            await asyncio.sleep(0.5)

            # FUZZY SELECTOR: Instead of specific module classes, look for any 
            # div that "looks" like a station container (contains a price and a heading)
            # We target divs that contain a '$' and have an 'h3' inside them.
            station_cards = await page.locator('div:has(h3):has-text("$")').all()
            
            gas_results: Dict[str, dict] = {}

            for card in station_cards:
                # Get the text but filter out huge chunks if the selector was too broad
                full_text = await card.inner_text()
                if len(full_text) > 1000: continue # Skip if it accidentally grabbed the whole page
                
                if "$" in full_text:
                    try:
                        # Fuzzy Name: Grab the first heading
                        name_el = card.locator('h3, h2, [class*="name"]').first
                        name = (await name_el.inner_text()).strip() if await name_el.count() > 0 else "Unknown"
                        
                        # Price extraction
                        price_match = re.search(r'\$(\d+\.\d+)', full_text)
                        if not price_match: continue
                        
                        # Address filtering and exclusions
                        address = "Unknown Address"
                        lines = [l.strip() for l in full_text.split('\n') if l.strip()]
                        
                        # Keywords to ignore (case-insensitive)
                        exclude_terms = ["AGO", "HOURS", "MIN", "SEC", "UPDATED", "REPORTED", "OWNER", "USER", "LOG IN"]
                        
                        for line in lines:
                            line_upper = line.upper()
                            
                            # 1. Skip if contains any exclusion keywords
                            if any(term in line_upper for term in exclude_terms):
                                continue
                            
                            # 2. Skip if it's just the price or the station name
                            if "$" in line or line.lower() == name.lower():
                                continue
                            
                            # 3. Fuzzy Address: Starts with a number, ends with text, and looks like a street
                            # Pattern: [Digits] [Space] [Letters/Numbers]
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
                    except:
                        continue

            # Sort and return top 3
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
    print(f"Searching for gas in {loc}...")
    results = asyncio.run(get_cheapest_gas(loc))
    
    if not results:
        print("No results found. Check if the site structure has changed significantly.")
    else:
        for i, r in enumerate(results, 1):
            tag = " (CASH)" if r['is_cash'] else ""
            print(f"{i}. ${r['price']:.2f}{tag} - {r['station']} @ {r['address']}")
