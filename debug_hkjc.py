import asyncio
from playwright.async_api import async_playwright

async def debug_hkjc():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        
        url = 'https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/01&Racecourse=ST&RaceNo=7'
        print(f'🎯 Testing: {url}')
        print('=' * 50)
        
        try:
            print('📡 Navigating...')
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            
            print(f'✅ Response Status: {response.status}')
            print(f'📄 URL after load: {page.url}')
            print(f'📊 Response headers: {dict(response.headers) if response else "N/A"}')
            
            await asyncio.sleep(2)
            
            html = await page.content()
            print(f'📃 HTML length: {len(html)} chars')
            
            # Check for common issues
            issues = []
            if '驗證碼' in html or 'captcha' in html.lower():
                issues.append('CAPTCHA detected')
            if '訪問被拒絕' in html:
                issues.append('Access denied')
            if '403' in html[:1000] or response.status == 403:
                issues.append('403 Forbidden')
            
            if issues:
                print(f'❌ Issues detected: {issues}')
            
            # Check for race data
            has_race_data = False
            if '賽事日期' in html:
                print('✅ Race data indicator found (賽事日期)')
                has_race_data = True
            if '賽果' in html:
                print('✅ Race results indicator found (賽果)')
                has_race_data = True
            if '名次' in html:
                print('✅ Rankings indicator found (名次)')
                has_race_data = True
                
            tables = await page.query_selector_all('table')
            print(f'📊 Tables found: {len(tables)}')
            
            if not has_race_data:
                print('⚠️ No race data indicators found')
                print(f'🔍 Content preview:\n{html[:500]}')
            
            print('=' * 50)
            print(f'📝 Final Result: {"✅ SUCCESS - Race data loaded" if has_race_data else "❌ FAILED - No race data"}')
                
        except Exception as e:
            print(f'❌ Error: {type(e).__name__}: {e}')
        
        await browser.close()

asyncio.run(debug_hkjc())
