"""
Collect ZhuYuan data - fixed version
"""

import asyncio
from playwright.async_api import async_playwright

async def collect_zhuyuan():
    url = "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=HK_2023_J256"
    
    print("🐴 抓取祝領 (HK_2023_J256) 所有資料")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        results = {}
        
        tabs = [
            ("往績紀錄", "race_history"),
            ("馬匹評分/體重/名次", "rating_history"),
            ("所跑途程賽績紀錄", "distance_stats"),
            ("晨操紀錄", "workouts"),
            ("傷患紀錄", "medical"),
            ("搬遷紀錄", "movements"),
            ("海外賽績紀錄", "overseas"),
            ("血統簡評", "pedigree"),
        ]
        
        for tab_name, key in tabs:
            print("\n" + "-" * 60)
            print("📊 {}".format(tab_name))
            print("-" * 60)
            
            try:
                await page.click("text={}".format(tab_name), timeout=5000)
                await asyncio.sleep(2)
                
                text = await page.inner_text("body")
                if any(msg in text for msg in ["沒有", "很抱歉", "暫未提供"]):
                    print("   ℹ️ 無此紀錄")
                    results[key] = 0
                    continue
                
                tables = await page.query_selector_all("table")
                count = 0
                
                for table in tables:
                    rows = await table.query_selector_all("tr")
                    if len(rows) > 1:
                        first_row = await rows[0].inner_text()
                        if any(k in first_row for k in ["場次", "日期", "途程", "評分", "馬場"]):
                            count = len(rows) - 1
                            print("   ✅ 找到 {} 行數據".format(count))
                            
                            # Show sample
                            for i in range(1, min(3, len(rows))):
                                cells = await rows[i].query_selector_all("td")
                                if cells:
                                    sample = [await c.inner_text() for c in cells[:4]]
                                    print("   樣本 {}: {}".format(i, " | ".join(sample)))
                            break
                
                if count == 0:
                    print("   ℹ️ 未找到數據 table")
                
                results[key] = count
                
            except Exception as e:
                print("   ⚠️ 錯誤: {}".format(str(e)[:50]))
                results[key] = 0
        
        await browser.close()
        
        print("\n" + "=" * 80)
        print("📊 抓取結果總結")
        print("=" * 80)
        for key, value in results.items():
            status = "✅" if value > 0 else "ℹ️"
            display = "{} 條/場".format(value) if value > 0 else "無紀錄/未找到"
            print("  {} {:20s}: {}".format(status, key, display))

if __name__ == "__main__":
    asyncio.run(collect_zhuyuan())
