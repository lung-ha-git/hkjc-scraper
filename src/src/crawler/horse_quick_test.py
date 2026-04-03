"""
Quick test for horse data collection
"""

import asyncio
from playwright.async_api import async_playwright

async def quick_test():
    url = "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2023_J256"
    
    print("🐴 Quick Test: 祝願 (HK_2023_J256)")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        print("\n📱 Loading page...")
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Find tabs by href
        print("\n📋 Finding tabs with links...")
        links = await page.query_selector_all("a[href*='#']")
        tabs_found = []
        
        for link in links:
            text = await link.inner_text()
            text = text.strip()
            if text and any(k in text for k in ["往績", "評分", "途程", "晨操", "傷患", "搬遷", "海外", "血統"]):
                href = await link.get_attribute("href")
                if text not in [t[0] for t in tabs_found]:
                    tabs_found.append((text, href))
                    print(f"  {text}: {href}")
        
        print(f"\n✅ Found {len(tabs_found)} tabs")
        
        # Test clicking first tab
        if tabs_found:
            tab_name, href = tabs_found[0]
            print(f"\n🖱️  Testing click on: {tab_name}")
            
            # Click by text
            try:
                await page.click(f"text={tab_name}")
                await asyncio.sleep(2)
                print("   ✓ Click successful")
                
                # Check what's visible now
                tables = await page.query_selector_all("table")
                print(f"   Tables visible: {len(tables)}")
                
                for i, table in enumerate(tables[:3]):
                    rows = await table.query_selector_all("tr")
                    if rows:
                        first_row = await rows[0].inner_text()
                        print(f"   Table {i}: {len(rows)} rows - {first_row[:50]}")
                
            except Exception as e:
                print(f"   ✗ Error: {e}")
        
        await browser.close()
        
        print("\n" + "=" * 80)
        print("✅ Quick test complete!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(quick_test())
