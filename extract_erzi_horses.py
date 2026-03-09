#!/usr/bin/env python3
"""
Extract all 2-character (二字馬) horse IDs from HKJC
"""

import asyncio
import re
from playwright.async_api import async_playwright

async def extract_erzi_horses():
    url = "https://racing.hkjc.com/zh-hk/local/information/selecthorse"
    
    print("🐴 Extracting all 二字馬 (2-character horses) from HKJC")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Click on "二字馬" link
        print("\n🖱️ Clicking on '二字馬' link...")
        try:
            erzi_link = await page.query_selector("text=二字馬")
            if erzi_link:
                await erzi_link.click()
                await asyncio.sleep(5)
                print("  ✅ Clicked 二字馬, waiting for data to load...")
            else:
                print("  ⚠️ Could not find 二字馬 link")
                await browser.close()
                return []
        except Exception as e:
            print(f"  ❌ Error clicking: {e}")
            await browser.close()
            return []
        
        # Extract all horse links
        print("\n🔎 Extracting horse data...")
        
        horses = []
        seen_ids = set()
        
        # Find all horse links
        links = await page.query_selector_all("a[href*='horse?horseid=']")
        
        for link in links:
            try:
                href = await link.get_attribute("href")
                horse_name = await link.inner_text()
                
                # Extract horse ID from URL
                match = re.search(r'horseid=([^&]+)', href or "")
                if match:
                    horse_id = match.group(1)
                    
                    # Skip duplicates
                    if horse_id in seen_ids:
                        continue
                    seen_ids.add(horse_id)
                    
                    # Clean up name
                    horse_name = horse_name.strip()
                    
                    if horse_name and len(horse_name) == 2:
                        horses.append({
                            "horse_id": horse_id,
                            "horse_name": horse_name
                        })
            except Exception as e:
                continue
        
        await browser.close()
        
        return horses


def main():
    horses = asyncio.run(extract_erzi_horses())
    
    print("\n" + "=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    
    print(f"\n✅ Total 二字馬 found: {len(horses)}")
    
    print(f"\n📋 First 20 horses:")
    print("-" * 40)
    for i, h in enumerate(horses[:20], 1):
        print(f"{i:2}. {h['horse_id']}: {h['horse_name']}")
    
    # Save to file
    import json
    output_file = "/Users/fatlung/.openclaw/workspace-main/hkjc_project/erzi_horses.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(horses, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Saved to: {output_file}")
    
    return horses


if __name__ == "__main__":
    main()
