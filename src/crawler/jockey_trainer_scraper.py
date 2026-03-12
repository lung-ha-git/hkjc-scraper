"""
HKJC Jockey and Trainer Scraper
Scrape all jockeys and trainers from HKJC

URL Patterns:
- Jockey: https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid=XXX
- Trainer: https://racing.hkjc.com/zh-hk/local/information/trainerprofile?trainerid=XXX

This scraper extracts:
1. All jockey IDs and basic info
2. All trainer IDs and basic info
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import List, Dict
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection


class JockeyTrainerScraper:
    """Scrape jockeys and trainers from HKJC"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def get_jockeys_from_page(self, page) -> List[Dict]:
        """Extract jockey links from a page"""
        jockeys = []
        
        # Find all jockey links
        links = await page.query_selector_all("a[href*='jockeyprofile?jockeyid=']")
        
        seen = set()
        for link in links:
            href = await link.get_attribute("href")
            match = re.search(r'jockeyid=([^&]+)', href or "")
            if not match:
                continue
            
            jockey_id = match.group(1)
            if jockey_id in seen:
                continue
            seen.add(jockey_id)
            
            name = await link.inner_text()
            name = name.strip()
            
            if name:
                jockeys.append({
                    "jockey_id": jockey_id,
                    "name": name,
                    "url": href
                })
        
        return jockeys
    
    async def get_trainers_from_page(self, page) -> List[Dict]:
        """Extract trainer links from a page"""
        trainers = []
        
        # Find all trainer links (try both patterns)
        links = await page.query_selector_all("a[href*='listbystable?trainerid='], a[href*='trainerprofile?trainerid=']")
        
        seen = set()
        for link in links:
            href = await link.get_attribute("href")
            match = re.search(r'trainerid=([A-Za-z0-9]+)', href or "")
            if not match:
                continue
            
            trainer_id = match.group(1)
            if trainer_id in seen:
                continue
            seen.add(trainer_id)
            
            name = await link.inner_text()
            name = name.strip()
            
            if name:
                trainers.append({
                    "trainer_id": trainer_id,
                    "name": name,
                    "url": href
                })
        
        return trainers
    
    async def _scrape_profile(self, profile_type: str, profile_id: str) -> Dict:
        """Common method to scrape jockey or trainer profile
        
        Args:
            profile_type: 'jockey' or 'trainer'
            profile_id: The jockey/trainer ID
            
        Returns:
            Dict with profile data
        """
        # Build URL based on type
        if profile_type == "jockey":
            url = f"https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid={profile_id}&season=Current"
            id_field = "jockey_id"
            name_indices = [33, 44]
            skip_names = []
            total_field = "total_rides"
        else:  # trainer
            url = f"https://racing.hkjc.com/zh-hk/local/information/trainerprofile?trainerid={profile_id}&season=Current"
            id_field = "trainer_id"
            name_indices = [33, 34, 35, 44, 45]
            skip_names = ['簡歷', '成績', '練馬師', '其他練馬師', '練馬師榜']
            total_field = "total_horses"
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            text = await page.inner_text("body")
            lines = text.split('\n')
            html = await page.content()
            
            profile = {
                id_field: profile_id,
                "url": url,
            }
            
            # Find name
            for i in name_indices:
                if i < len(lines) and lines[i].strip():
                    if skip_names and lines[i].strip() in skip_names:
                        continue
                    profile["name"] = lines[i].strip()
                    break
            
            # Extract stats from HTML (same for both)
            import re
            
            # Wins
            win_match = re.search(r'冠</td>\s*<td[^>]*>:\s*(\d+)</td>', html)
            if win_match:
                profile["wins"] = int(win_match.group(1))
            
            # Seconds
            sec_match = re.search(r'亞</td>\s*<td[^>]*>:\s*(\d+)</td>', html)
            if sec_match:
                profile["seconds"] = int(sec_match.group(1))
            
            # Thirds
            third_match = re.search(r'季</td>\s*<td[^>]*>:\s*(\d+)</td>', html)
            if third_match:
                profile["thirds"] = int(third_match.group(1))
            
            # Total
            if profile_type == "jockey":
                total_match = re.search(r'總出賽次數</td>\s*<td[^>]*>:\s*(\d+)</td>', html)
            else:
                total_match = re.search(r'馬房總數</td>\s*<td[^>]*>:\s*(\d+)</td>', html)
            
            if total_match:
                profile[total_field] = int(total_match.group(1))
            
            # Prize money
            prize_match = re.search(r'所贏獎金</td>\s*<td[^>]*>:\s*\$?([\d,]+)</td>', html)
            if prize_match:
                profile["prize_money"] = prize_match.group(1)
                profile["prize_money_int"] = int(prize_match.group(1).replace(",", ""))
            
            profile["scraped_at"] = datetime.now().isoformat()
            
            await context.close()
            return profile
            
        except Exception as e:
            await context.close()
            return {id_field: profile_id, "error": str(e)}
    
    async def scrape_jockey(self, jockey_id: str) -> Dict:
        """Scrape detailed info for a single jockey"""
        return await self._scrape_profile("jockey", jockey_id)
    
    async def scrape_trainer(self, trainer_id: str) -> Dict:
        """Scrape detailed info for a single trainer"""
        return await self._scrape_profile("trainer", trainer_id)
    
    async def scrape_all_jockeys(self) -> List[Dict]:
        """Scrape all jockeys from main pages"""
        print("\n👤 Scraping all jockeys...")
        
        # First get list from a page that has all jockeys
        url = "https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid=BH"
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Get jockeys from "其他騎師" section
        jockeys = await self.get_jockeys_from_page(page)
        
        await context.close()
        
        print(f"   Found {len(jockeys)} jockey links")
        
        # Now scrape each jockey
        results = []
        semaphore = asyncio.Semaphore(3)
        
        async def scrape_with_limit(jockey):
            async with semaphore:
                return await self.scrape_jockey(jockey["jockey_id"])
        
        tasks = [scrape_with_limit(j) for j in jockeys]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = [r for r in results if isinstance(r, dict) and "error" not in r]
        print(f"   ✅ Scraped {len(successful)} jockeys successfully")
        
        return successful
    
    async def scrape_all_trainers(self) -> List[Dict]:
        """Scrape all trainers"""
        print("\n🏇 Scraping all trainers...")
        
        # Get from selecthorse page which has trainer list
        url = "https://racing.hkjc.com/zh-hk/local/information/selecthorse"
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        trainers = await self.get_trainers_from_page(page)
        
        await context.close()
        
        print(f"   Found {len(trainers)} trainer links")
        
        # Scrape each trainer
        results = []
        semaphore = asyncio.Semaphore(3)
        
        async def scrape_with_limit(trainer):
            async with semaphore:
                return await self.scrape_trainer(trainer["trainer_id"])
        
        tasks = [scrape_with_limit(t) for t in trainers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = [r for r in results if isinstance(r, dict) and "error" not in r]
        print(f"   ✅ Scraped {len(successful)} trainers successfully")
        
        return successful
    
    async def save_to_mongodb(self, jockeys: List[Dict], trainers: List[Dict]):
        """Save to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        # Save jockeys
        if jockeys:
            db.db["jockeys"].delete_many({})
            db.db["jockeys"].insert_many(jockeys)
            print(f"   ✅ jockeys: {len(jockeys)} records")
        
        # Save trainers
        if trainers:
            db.db["trainers"].delete_many({})
            db.db["trainers"].insert_many(trainers)
            print(f"   ✅ trainers: {len(trainers)} records")
        
        db.disconnect()
        print("\n✅ Done!")


async def main():
    """Main entry point"""
    async with JockeyTrainerScraper(headless=True) as scraper:
        # Scrape jockeys
        jockeys = await scraper.scrape_all_jockeys()
        
        # Scrape trainers
        trainers = await scraper.scrape_all_trainers()
        
        # Save to MongoDB
        await scraper.save_to_mongodb(jockeys, trainers)
        
        print("\n" + "=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Jockeys: {len(jockeys)}")
        print(f"Trainers: {len(trainers)}")


if __name__ == "__main__":
    asyncio.run(main())
