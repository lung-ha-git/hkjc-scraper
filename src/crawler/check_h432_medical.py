"""
Check medical records for HK_2022_H432
"""

import asyncio
from playwright.async_api import async_playwright

async def check_medical_v2():
    url = "https://racing.hkjc.com/zh-hk/local/information/ovehorse?horseid=HK_2022_H432"
    
    print("🩸 重新檢查 H432 傷患紀錄 (v2)")
    print("=" * 80)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(url, wait_until="networkidle")
        await asyncio.sleep(3)
        
        # Get full text content
        text = await page.inner_text("body")
        
        # Check for no data messages
        print("\n📄 頁面內容分析:")
        
        no_data_msgs = ["找不到資料", "沒有", "很抱歉", "暫未提供"]
        found_msgs = [m for m in no_data_msgs if m in text]
        
        if found_msgs:
            print(f"  ✅ 找到無資料訊息: {found_msgs}")
        else:
            print("  ℹ️  未找到無資料訊息")
        
        # Check for medical keywords
        medical_keywords = ["傷患", "獸醫", "受傷", "不貝", "治理"]
        found_keywords = [k for k in medical_keywords if k in text]
        
        print(f"  傷患關鍵詞: {found_keywords if found_keywords else '無'}")
        
        # Check tables
        tables = await page.query_selector_all("table")
        print(f"\n📊 分析 {len(tables)} 個 tables:")
        
        valid_medical_table = None
        medical_count = 0
        
        for i, table in enumerate(tables):
            rows = await table.query_selector_all("tr")
            if len(rows) <= 1:
                continue
            
            # Skip navigation tables
            header_cells = await rows[0].query_selector_all("th, td")
            header_text = " ".join([await c.inner_text() for c in header_cells])
            
            # Skip if contains navigation terms
            if any(nav in header_text for nav in ["往績紀錄", "馬匹評分", "晨操紀錄"]):
                continue
            
            # Check for medical indicators
            if any(k in header_text for k in ["日期", "傷患", "部位", "治療"]):
                print(f"  Table {i}: {len(rows)-1} rows")
                print(f"    Header: {header_text[:60]}")
                
                valid_medical_table = table
                medical_count = len(rows) - 1
                
                # Show sample
                for j in range(1, min(4, len(rows))):
                    cells = await rows[j].query_selector_all("td")
                    if len(cells) >= 2:
                        row_text = " | ".join([await c.inner_text() for c in cells[:3]])
                        print(f"    Row {j}: {row_text[:60]}")
                
                break
        
        if valid_medical_table is None:
            print("  ℹ️  未找到有效傷患 table")
            medical_count = 0
        
        await browser.close()
        
        print("\n" + "=" * 80)
        print(f"📋 結論: H432 傷患紀錄 = {medical_count} 條")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(check_medical_v2())
