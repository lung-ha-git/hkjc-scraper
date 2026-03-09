"""Test horse detail extraction"""
import asyncio
import re
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        horse_id = 'HK_2023_J062'
        url = f'https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}'
        await page.goto(url, wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        text = await page.inner_text('body')
        title = await page.title()
        
        horse_data = {'hkjc_horse_id': horse_id}
        
        # Name - from title
        title_match = re.search(r'^([^-]+)', title)
        if title_match:
            horse_data['name'] = title_match.group(1).strip()
        
        # 出生地 / 馬齡
        origin_age_match = re.search(r'出生地\s*/\s*馬齡\s*[:：]\s*([^\s/]+)\s*/\s*(\d+)', text)
        if origin_age_match:
            horse_data['country_of_origin'] = origin_age_match.group(1).strip()
            horse_data['age'] = int(origin_age_match.group(2).strip())
        
        # 毛色 / 性別
        color_sex_match = re.search(r'毛色\s*/\s*性別\s*[:：]\s*([^\s/]+)\s*/\s*(\S+)', text)
        if color_sex_match:
            horse_data['color'] = color_sex_match.group(1).strip()
            horse_data['sex'] = color_sex_match.group(2).strip()
        
        # 進口類別
        import_type_match = re.search(r'進口類別\s*[:：]\s*([^\n]+)', text)
        if import_type_match:
            horse_data['import_type'] = import_type_match.group(1).strip()
        
        # 今季獎金
        season_prize_match = re.search(r'今季獎金.*?:\s*\$?([\d,]+)', text)
        if season_prize_match:
            horse_data['season_prize'] = int(season_prize_match.group(1).replace(',', ''))
        
        # 總獎金
        total_prize_match = re.search(r'總獎金.*?:\s*\$?([\d,]+)', text)
        if total_prize_match:
            horse_data['total_prize'] = int(total_prize_match.group(1).replace(',', ''))
        
        # 冠-亞-季-總出賽次數
        career_match = re.search(r'冠-亞-季-總出賽次數.*?(\d+)-(\d+)-(\d+)-(\d+)', text)
        if career_match:
            horse_data['career_wins'] = int(career_match.group(1))
            horse_data['career_seconds'] = int(career_match.group(2))
            horse_data['career_thirds'] = int(career_match.group(3))
            horse_data['career_starts'] = int(career_match.group(4))
        
        # 現時評分
        current_rating_match = re.search(r'現時評分\s*[:：]\s*(\d+)', text)
        if current_rating_match:
            horse_data['current_rating'] = int(current_rating_match.group(1))
        
        # 季初評分
        season_start_rating_match = re.search(r'季初評分\s*[:：]\s*(\d+)', text)
        if season_start_rating_match:
            horse_data['season_start_rating'] = int(season_start_rating_match.group(1))
        
        # 父系
        sire_match = re.search(r'父系\s*[:：]\s*([^\n]+)', text)
        if sire_match:
            horse_data['sire'] = sire_match.group(1).strip()
        
        # 母系
        dam_match = re.search(r'母系\s*[:：]\s*([^\n]+)', text)
        if dam_match:
            horse_data['dam'] = dam_match.group(1).strip()
        
        # 外祖父
        mgs_match = re.search(r'外祖父\s*[:：]\s*([^\n]+)', text)
        if mgs_match:
            horse_data['maternal_grand_sire'] = mgs_match.group(1).strip()
        
        # 練馬師
        trainer_match = re.search(r'練馬師\s*[:：]\s*([^\n]+)', text)
        if trainer_match:
            horse_data['trainer'] = trainer_match.group(1).strip()
        
        # 馬主
        owner_match = re.search(r'馬主\s*[:：]\s*([^\n]+)', text)
        if owner_match:
            horse_data['owner'] = owner_match.group(1).strip()
        
        await browser.close()
        
        print('=== Extracted Horse Data ===')
        for k, v in horse_data.items():
            print(f'{k}: {v}')

asyncio.run(test())
