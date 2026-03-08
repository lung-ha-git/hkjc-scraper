import asyncio
from playwright.async_api import async_playwright

async def debug_hkjc():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = 'https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/01&Racecourse=ST&RaceNo=7'
        print(f'Testing: {url}')
        
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f'\n=== PAGE STATUS ===')
            print(f'Status Code: {response.status}')
            print(f'Final URL: {page.url}')
            
            await asyncio.sleep(5)
            
            html = await page.content()
            print(f'\n=== CONTENT INFO ===')
            print(f'HTML Length: {len(html)} bytes')
            
            # Check for key indicators
            print(f'\n=== CONTENT CHECKS ===')
            print(f'Contains "賽事日期": {"賽事日期" in html}')
            print(f'Contains "頭馬": {"頭馬" in html}')
            print(f'Contains "馬號": {"馬號" in html}')
            print(f'Contains "馬名": {"馬名" in html}')
            print(f'Contains "captcha/驗證碼": {"captcha" in html.lower() or "驗證碼" in html}')
            
            # Count tables
            tables = await page.query_selector_all('table')
            print(f'\n=== TABLES ===')
            print(f'Table count: {len(tables)}')
            
            # Get page title
            title = await page.title()
            print(f'\n=== PAGE TITLE ===')
            print(f'Title: {title}')
            
            # Check for race data
            if '賽事日期' in html or '頭馬' in html:
                print('\n✅ RACE DATA PRESENT!')
            elif 'captcha' in html.lower() or '驗證碼' in html:
                print('\n❌ CAPTCHA DETECTED!')
            else:
                print('\n⚠️ NO CLEAR RACE DATA FOUND')
                # Show a snippet
                print('\n=== HTML SNIPPET (first 800 chars) ===')
                print(html[:800])
                
        except Exception as e:
            print(f'Error: {type(e).__name__}: {e}')
        
        await browser.close()

asyncio.run(debug_hkjc())
