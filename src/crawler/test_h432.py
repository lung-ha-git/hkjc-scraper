"""
Test scraping horse HK_2022_H432
"""

import asyncio
import re
from playwright.async_api import async_playwright

async def test_h432():
    hkjc_id = "HK_2022_H432"
    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={hkjc_id}"
    
    print("🐴 測試抓取: HK_2022_H432")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Get basic info
        print("\n📋 基本資料:")
        
        # Try to get from title or content
        content = await page.content()
        text = await page.inner_text("body")
        
        # Extract name
        name_match = re.search(r'<h1[^>]*>(.+?)</h1>', content, re.DOTALL)
        if name_match:
            name = re.sub(r'<[^>]+>', '', name_match.group(1))
            print(f"  馬名: {name.strip()}")
        
        # Extract other info
        info_patterns = [
            ("出生地/馬齡", r'出生地\s*/\s*馬齡\s*[:：]\s*([^/\n]+)\s*/\s*(\d+)'),
            ("毛色/性別", r'毛色\s*/\s*性別\s*[:：]\s*([^/\n]+)\s*/\s*([^\n]+)'),
            ("練馬師", r'練馬師\s*[:：]\s*([^\n]+)'),
            ("現時評分", r'現時評分\s*[:：]\s*(\d+)'),
        ]
        
        for label, pattern in info_patterns:
            match = re.search(pattern, text)
            if match:
                if label == "出生地/馬齡":
                    print(f"  出生地: {match.group(1).strip()}")
                    print(f"  馬齡: {match.group(2)}")
                elif label == "毛色/性別":
                    print(f"  毛色: {match.group(1).strip()}")
                    print(f"  性別: {match.group(2).strip()}")
                else:
                    print(f"  {label}: {match.group(1).strip()}")
        
        # Race history
        print("\n🏇 往績紀錄:")
        tables = await page.query_selector_all("table.bigborder")
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) > 1:
                valid_count = 0
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if cells:
                        first = await cells[0].inner_text()
                        if re.match(r'^\d+$', first.strip()):
                            valid_count += 1
                
                print(f"  ✅ {valid_count} 場比賽")
                
                # Show sample
                if valid_count > 0:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 5:
                            first = await cells[0].inner_text()
                            if re.match(r'^\d+$', first.strip()):
                                race_no = first.strip()
                                date = await cells[2].inner_text()
                                position = await cells[1].inner_text()
                                jockey = await cells[10].inner_text() if len(cells) > 10 else "N/A"
                                print(f"  樣本: 場次{race_no} | {date.strip()} | 第{position.strip()}名 | {jockey.strip()}")
                                break
                break
        
        # Available tabs
        print("\n📑 Available tabs from page:")
        tabs_keywords = ["往績", "評分", "途程", "晨操", "傷患", "搬遷", "血統"]
        for keyword in tabs_keywords:
            if keyword in text:
                print(f"  ✅ {keyword}")
        
        await browser.close()
        
        print("\n" + "=" * 80)
        print("✅ 測試完成!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_h432())
