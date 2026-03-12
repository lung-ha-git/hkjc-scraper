"""
HKJC Horse Detail Scraper
Scrape individual horse detail pages
URL pattern: https://racing.hkjc.com/zh-hk/local/information/horse?horseid=XXX
"""

import asyncio
import re
from playwright.async_api import async_playwright
from datetime import datetime
from typing import Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HorseDetailScraper:
    """Scraper for individual horse detail pages"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
    
    async def scrape_horse_detail(self, horse_id: str) -> Optional[Dict]:
        """
        Scrape detail page for a specific horse
        
        Args:
            horse_id: HKJC horse ID (e.g., "S927" or internal ID)
            
        Returns:
            Dict with horse details or None
        """
        url = f"{self.BASE_URL}?horseid={horse_id}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                logger.info(f"Scraping horse: {horse_id}")
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(self.delay * 1000)
                
                # Extract all horse details
                horse_data = await self._extract_details(page, horse_id)
                
                await browser.close()
                return horse_data
                
            except Exception as e:
                logger.error(f"Error scraping horse {horse_id}: {e}")
                await browser.close()
                return None
    
    async def _extract_details(self, page, horse_id: str) -> Dict:
        """Extract all details from horse page"""
        
        data = {
            "hkjc_horse_id": horse_id,
            "scraped_at": datetime.now().isoformat(),
            "url": page.url
        }
        
        # Get page content
        content = await page.content()
        text = await page.inner_text("body")
        
        # Extract basic info section
        data.update(await self._extract_basic_info(text))
        
        # Extract pedigree
        data.update(await self._extract_pedigree(text))
        
        # Extract stats
        data.update(await self._extract_stats(text))
        
        # Extract current season info
        data.update(await self._extract_season_info(text))
        
        return data
    
    async def _extract_basic_info(self, text: str) -> Dict:
        """Extract basic info: 出生地, 馬齡, 毛色, 性別, etc. (Traditional Chinese)"""
        info = {}
        
        # Pattern: 出生地 / 馬齡：愛爾蘭 / 4 (Traditional)
        match = re.search(r'出生地\s*/\s*馬齡\s*[:：]\s*(.+?)\s*/\s*(\d+)', text)
        if not match:
            # Try Simplified Chinese
            match = re.search(r'出生地\s*/\s*马龄\s*[:：]\s*(.+?)\s*/\s*(\d+)', text)
        
        if match:
            info["country"] = match.group(1).strip()
            info["age"] = int(match.group(2))
        
        # Pattern: 毛色 / 性別：棗 / 雄 (Traditional)
        match = re.search(r'毛色\s*/\s*性別\s*[:：]\s*(.+?)\s*/\s*(.+?)(?:\n|$)', text)
        if not match:
            # Try Simplified Chinese
            match = re.search(r'毛色\s*/\s*性别\s*[:：]\s*(.+?)\s*/\s*(.+?)(?:\n|$)', text)
        
        if match:
            info["color"] = match.group(1).strip()
            sex_map = {"閹": "G", "閹馬": "G", "騙": "G", "雄": "H", "雌": "F", "公": "H", "母": "F"}
            sex_raw = match.group(2).strip()
            info["sex"] = sex_map.get(sex_raw, sex_raw)
        
        # Pattern: 進口類別：自購馬 (Traditional)
        match = re.search(r'進口類別\s*[:：]\s*(.+?)(?:\n|$)', text)
        if not match:
            match = re.search(r'进口类别\s*[:：]\s*(.+?)(?:\n|$)', text)
        
        if match:
            info["import_type"] = match.group(1).strip()
        
        # Pattern: 練馬師：姚本輝 (Traditional)
        match = re.search(r'練馬師\s*[:：]\s*(.+?)(?:\n|$)', text)
        if not match:
            match = re.search(r'练马师\s*[:：]\s*(.+?)(?:\n|$)', text)
        
        if match:
            info["trainer"] = match.group(1).strip()
        
        # Pattern: 馬主：君匯團體 (Traditional)
        match = re.search(r'馬主\s*[:：]\s*(.+?)(?:\n|$)', text)
        if not match:
            match = re.search(r'马主\s*[:：]\s*(.+?)(?:\n|$)', text)
        
        if match:
            info["owner"] = match.group(1).strip()
        
        # Pattern: 進口日期：16/09/2024 (Traditional)
        match = re.search(r'進口日期\s*[:：]\s*(\d{2}/\d{2}/\d{4})', text)
        if not match:
            match = re.search(r'进口日期\s*[:：]\s*(\d{2}/\d{2}/\d{4})', text)
        
        if match:
            info["import_date"] = match.group(1)
        
        return info
    
    async def _extract_pedigree(self, text: str) -> Dict:
        """Extract pedigree info: 父系, 母系, 外祖父 (Traditional Chinese)"""
        pedigree = {}
        
        # Pattern: 父系：Alabama Express (Traditional)
        match = re.search(r'父系\s*[:：]\s*(.+?)(?:\n|$)', text)
        if match:
            pedigree["sire"] = match.group(1).strip()
        
        # Pattern: 母系：World Awaits (Traditional)
        match = re.search(r'母系\s*[:：]\s*(.+?)(?:\n|$)', text)
        if match:
            pedigree["dam"] = match.group(1).strip()
        
        # Pattern: 外祖父：Written Tycoon (Traditional)
        match = re.search(r'外祖父\s*[:：]\s*(.+?)(?:\n|$)', text)
        if match:
            pedigree["damsire"] = match.group(1).strip()
        
        return {"pedigree": pedigree}
    
    async def _extract_stats(self, text: str) -> Dict:
        """Extract stats: 今季奖金, 总奖金, 出赛次数等"""
        stats = {}
        
        # Pattern: 今季獎金*：$604,500 (Traditional)
        match = re.search(r'今季獎金\*?\s*[:：]\s*\$?([\d,]+)', text)
        if not match:
            match = re.search(r'今季奖金\*?\s*[:：]\s*\$?([\d,]+)', text)
        
        if match:
            stats["season_prize_money"] = int(match.group(1).replace(",", ""))
        
        # Pattern: 總獎金*：$604,500 (Traditional)
        match = re.search(r'總獎金\*?\s*[:：]\s*\$?([\d,]+)', text)
        if not match:
            match = re.search(r'总奖金\*?\s*[:：]\s*\$?([\d,]+)', text)
        
        if match:
            stats["total_prize_money"] = int(match.group(1).replace(",", ""))
        
        # Pattern: 冠-亞-季-總出賽次數*：0-0-2-8 (Traditional)
        match = re.search(r'冠.*亞.*季.*總出賽次數\*?\s*[:：]\s*(\d+)-(\d+)-(\d+)-(\d+)', text)
        if not match:
            match = re.search(r'冠.*亚.*季.*总出赛次数\*?\s*[:：]\s*(\d+)-(\d+)-(\d+)-(\d+)', text)
        
        if match:
            stats["wins"] = int(match.group(1))
            stats["seconds"] = int(match.group(2))
            stats["thirds"] = int(match.group(3))
            stats["total_starts"] = int(match.group(4))
        
        # Current and initial rating
        match = re.search(r'現時評分\s*[:：]\s*(\d+)', text)
        if not match:
            match = re.search(r'现在评分\s*[:：]\s*(\d+)', text)
        
        if match:
            stats["current_rating"] = int(match.group(1))
        
        match = re.search(r'季初評分\s*[:：]\s*(\d+)', text)
        if not match:
            match = re.search(r'季初评分\s*[:：]\s*(\d+)', text)
        
        if match:
            stats["initial_rating"] = int(match.group(1))
        
        return {"stats": stats}
    
    async def _extract_season_info(self, text: str) -> Dict:
        """Extract recent season info (Traditional Chinese)"""
        info = {}
        
        # Pattern: 最近十個賽馬日出賽場數：0 (Traditional)
        match = re.search(r'最近十個賽馬日\s*出賽場數\s*[:：]\s*(\d+)', text)
        if not match:
            match = re.search(r'最近十个赛马日\s*出赛场数\s*[:：]\s*(\d+)', text)
        
        if match:
            info["recent_10_runs"] = int(match.group(1))
        
        # Location (Traditional)
        match = re.search(r'現在位置\s*\(到達日期\)\s*[:：]\s*(.+?)\s*\((\d{2}/\d{2}/\d{4})\)', text)
        if not match:
            match = re.search(r'现在位置\s*\(到达日期\)\s*[:：]\s*(.+?)\s*\((\d{2}/\d{2}/\d{4})\)', text)
        
        if match:
            info["current_location"] = match.group(1).strip()
            info["arrival_date"] = match.group(2)
        
        return {"season_info": info}


# Test function
async def test_scraper():
    """Test with a sample horse"""
    scraper = HorseDetailScraper()
    
    # Test with horse ID (you'll need real HKJC horse IDs)
    # Example: S927
    test_id = "S927"
    
    print(f"🐴 Testing horse detail scraper with ID: {test_id}")
    print("=" * 60)
    
    try:
        data = await scraper.scrape_horse_detail(test_id)
        if data:
            print("✅ Successfully scraped!")
            print("\n📋 Extracted data:")
            print(f"  HKJC ID: {data.get('hkjc_horse_id')}")
            print(f"  Basic: {data.get('country')}, {data.get('age')}岁, {data.get('sex')}")
            print(f"  Trainer: {data.get('trainer')}")
            print(f"  Stats: {data.get('stats', {})}")
            print(f"  Pedigree: {data.get('pedigree', {})}")
        else:
            print("⚠️  No data returned")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_scraper())
