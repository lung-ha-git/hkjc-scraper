#!/usr/bin/env python3
"""
Test script to inspect HKJC selecthorse page structure
"""

import asyncio
from playwright.async_api import async_playwright

async def inspect_page():
    url = "https://racing.hkjc.com/zh-hk/local/information/selecthorse?HorseNameLen=2"
    
    print("🔍 Inspecting HKJC selecthorse page...")
    print(f"URL: {url}")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: print(f"[Console] {msg.type}: {msg.text}"))
        
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(5)  # Wait for JS to load
        
        # Click on "二字馬" link
        print("\n🖱️ Clicking on '二字馬' link...")
        try:
            erzi_link = await page.query_selector("text=二字馬")
            if erzi_link:
                await erzi_link.click()
                await asyncio.sleep(5)
                print("  ✅ Clicked 二字馬")
            else:
                print("  ⚠️ Could not find 二字馬 link")
        except Exception as e:
            print(f"  ⚠️ Error clicking: {e}")
        
        # Get page title
        title = await page.title()
        print(f"\n📄 Page Title: {title}")
        
        # Look for horse links
        print("\n🔎 Looking for horse links...")
        
        # Try different selectors
        selectors = [
            "a[href*='horse?horseid=']",
            "a[href*='Horse']",
            "a[href*='horseid']",
            ".horse-name",
            "[class*='horse']",
            "table tr a",
            ".horseList a",
            "#horseList a",
            ".content a",
        ]
        
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            print(f"  {selector}: {len(elements)} elements")
            
            if elements and len(elements) > 0:
                print(f"    Sample:")
                for i, el in enumerate(elements[:3]):
                    href = await el.get_attribute("href")
                    text = await el.inner_text()
                    print(f"      [{i}] {text[:30]} -> {href[:50] if href else 'N/A'}")
        
        # Get page HTML content
        print("\n📝 Page HTML (first 3000 chars):")
        html = await page.content()
        print(html[:3000])
        
        # Look for any table data
        print("\n📊 Looking for tables...")
        tables = await page.query_selector_all("table")
        print(f"  Found {len(tables)} tables")
        
        for i, table in enumerate(tables[:3]):
            rows = await table.query_selector_all("tr")
            print(f"    Table {i}: {len(rows)} rows")
            if rows:
                header = await rows[0].inner_text()
                print(f"      Header: {header[:100]}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_page())
