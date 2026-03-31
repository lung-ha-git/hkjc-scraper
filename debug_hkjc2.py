import asyncio
from playwright.async_api import async_playwright

async def debug_hkjc():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        url = 'https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/01&Racecourse=ST&RaceNo=7'
        print(f'Testing: {url}')
        
        try:
            # Try with domcontentloaded instead of networkidle
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f'Status: {response.status}')
            print(f'URL after load: {page.url}')
            
            await asyncio.sleep(5)
            
            html = await page.content()
            print(f'HTML length: {len(html)}')
            
            if '驗證碼' in html or 'captcha' in html.lower():
                print('❌ CAPTCHA detected!')
            elif '訪問被拒絕' in html or '403' in html:
                print('❌ Access denied (403)!')
            elif '賽事日期' in html or 'race' in html.lower():
                print('✅ Racing content detected!')
                # Check for results table
                titles = await page.query_selector_all('h3, h2, h1')
                print(f'Headers found: {len(titles)}')
                for i, t in enumerate(titles[:3]):
                    text = await t.text_content()
                    print(f'  Header {i+1}: {text[:50]}...' if text else f'  Header {i+1}: (empty)')
            else:
                print('⚠️ Unknown content - first 500 chars:')
                print(html[:500])
                
        except Exception as e:
            print(f'Error: {type(e).__name__}: {e}')
        
        await browser.close()

asyncio.run(debug_hkjc())
