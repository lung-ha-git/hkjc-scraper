"""
HKJC Complete Scraper Workflow
=============================
Phase 1: Jockeys & Trainers
Phase 2: Horse List (二字馬)
Phase 3: Horse Details + Race URLs
Phase 4: Race Results

Usage:
    python3 src/crawler/hkjc_complete_scraper.py

Author: OpenClaw
Date: 2026-03-09
"""

import asyncio
import re
from datetime import datetime
from typing import List, Dict, Set
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from playwright.async_api import async_playwright


class HKJCCompleteScraper:
    """Complete HKJC scraper workflow"""
    
    def __init__(self, max_concurrent: int = 2, headless: bool = True):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.db = None
        
        # Track progress
        self.stats = {
            "jockeys": 0,
            "trainers": 0,
            "horses": 0,
            "races": 0,
            "errors": []
        }
    
    async def run(self):
        """Run complete workflow"""
        print("\n" + "=" * 70)
        print("🏇 HKJC COMPLETE SCRAPER")
        print("=" * 70)
        
        # Connect to DB
        self.db = DatabaseConnection()
        if not self.db.connect():
            print("❌ Cannot connect to MongoDB")
            return
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                # Phase 1: Jockeys & Trainers
                await self.scrape_jockeys_trainers(browser)
                
                # Phase 2: Horse List (二字馬)
                horse_ids = await self.scrape_horse_list(browser)
                
                # Phase 3: Horse Details + Race URLs
                race_urls = await self.scrape_horses_details(browser, horse_ids)
                
                # Phase 4: Race Results
                await self.scrape_races(browser, race_urls)
                
            finally:
                await browser.close()
        
        self.db.disconnect()
        
        # Print summary
        self.print_summary()
    
    async def scrape_jockeys_trainers(self, browser):
        """Phase 1: Scrape jockeys and trainers"""
        print("\n📋 PHASE 1: Jockeys & Trainers")
        print("-" * 50)
        
        page = await browser.new_page()
        
        # Scrape jockeys
        print("👤 Scraping jockeys...")
        await page.goto("https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid=BH", 
                       wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        # Get jockey links
        jockey_links = await page.query_selector_all("a[href*='jockeyprofile?jockeyid=']")
        jockeys = []
        seen_jockeys = set()
        
        for link in jockey_links:
            href = await link.get_attribute("href")
            match = re.search(r'jockeyid=([^&]+)', href or "")
            if match and match.group(1) not in seen_jockeys:
                seen_jockeys.add(match.group(1))
                name = (await link.inner_text()).strip()
                if name:
                    jockeys.append({"jockey_id": match.group(1), "name": name})
        
        # Save jockeys
        self.db.db["jockeys"].delete_many({})
        if jockeys:
            self.db.db["jockeys"].insert_many(jockeys)
        self.stats["jockeys"] = len(jockeys)
        print(f"   ✅ {len(jockeys)} jockeys")
        
        # Scrape trainers from selecthorse page
        print("🏇 Scraping trainers...")
        await page.goto("https://racing.hkjc.com/zh-hk/local/information/selecthorse",
                       wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        trainer_links = await page.query_selector_all("a[href*='listbystable?trainerid=']")
        trainers = []
        seen_trainers = set()
        
        for link in trainer_links:
            href = await link.get_attribute("href")
            match = re.search(r'trainerid=([^&]+)', href or "")
            if match and match.group(1) not in seen_trainers:
                seen_trainers.add(match.group(1))
                name = (await link.inner_text()).strip()
                if name:
                    trainers.append({"trainer_id": match.group(1), "name": name})
        
        # Save trainers
        self.db.db["trainers"].delete_many({})
        if trainers:
            self.db.db["trainers"].insert_many(trainers)
        self.stats["trainers"] = len(trainers)
        print(f"   ✅ {len(trainers)} trainers")
        
        await page.close()
    
    async def scrape_horse_list(self, browser) -> List[str]:
        """Phase 2: Get ALL horse list (一字/二字/三字/四字)"""
        print("\n📋 PHASE 2: Horse List (ALL - 一字/二字/三字/四字)")
        print("-" * 50)
        
        page = await browser.new_page()
        
        # Go to selecthorse page and get ALL horses
        print("🔍 Getting ALL horses from HKJC...")
        
        await page.goto("https://racing.hkjc.com/zh-hk/local/information/selecthorse",
                       wait_until="domcontentloaded")
        await asyncio.sleep(3)
        
        # Method: Click through different name length filters
        # Or get ALL horse links from the page
        
        # First try: Get all horse links directly
        all_links = await page.query_selector_all("a[href*='horse?horseid=']")
        
        horse_ids = []
        seen = set()
        
        for link in all_links:
            href = await link.get_attribute("href")
            match = re.search(r'horseid=([^&/]+)', href or "")
            
            if match:
                horse_id = match.group(1)
                # Filter out non-HK horse IDs (like HK_2020_XXX)
                if horse_id.startswith("HK_") and horse_id not in seen:
                    seen.add(horse_id)
                    horse_ids.append(horse_id)
        
        # If not enough, try clicking filters
        if len(horse_ids) < 50:
            print(f"   Found {len(horse_ids)}, trying filters...")
            
            # Try to find and click name length filter links (二字馬/三字馬/四字馬)
            name_lengths = ["二字馬", "三字馬", "四字馬"]
            
            for length in name_lengths:
                try:
                    await page.goto("https://racing.hkjc.com/zh-hk/local/information/selecthorse",
                                   wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    
                    # Click the filter
                    filter_link = await page.query_selector(f"text={length}")
                    if filter_link:
                        await filter_link.click()
                        await asyncio.sleep(3)
                        
                        # Get links
                        links = await page.query_selector_all("a[href*='horse?horseid=']")
                        
                        for link in links:
                            href = await link.get_attribute("href")
                            match = re.search(r'horseid=([^&/]+)', href or "")
                            
                            if match:
                                horse_id = match.group(1)
                                if horse_id.startswith("HK_") and horse_id not in seen:
                                    seen.add(horse_id)
                                    horse_ids.append(horse_id)
                        
                        print(f"   {length}: +{len(links)} horses")
                except Exception as e:
                    print(f"   Error with {length}: {e}")
        
        # Remove duplicates
        horse_ids = list(set(horse_ids))
        
        self.stats["horses"] = len(horse_ids)
        print(f"   ✅ Total: {len(horse_ids)} horses ready")
        
        await page.close()
        return horse_ids
    
    async def scrape_horses_details(self, browser, horse_ids: List[str]) -> Dict:
        """Phase 3: Scrape horse details and extract race URLs"""
        print("\n📋 PHASE 3: Horse Details + Race URLs")
        print("-" * 50)
        
        race_urls = {}  # race_id -> {url, date, source_horses}
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_horse(horse_id: str):
            async with semaphore:
                page = await browser.new_page()
                
                try:
                    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}"
                    await page.goto(url, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    
                    text = await page.inner_text("body")
                    
                    # Extract basic info
                    horse_data = {"hkjc_horse_id": horse_id}
                    
                    # Name
                    name_match = re.search(r'^([^\n(]+)', text)
                    if name_match:
                        horse_data["name"] = name_match.group(1).strip()
                    
                    # Trainer
                    trainer_match = re.search(r'練馬師\s*[:：]\s*([^\n]+)', text)
                    if trainer_match:
                        horse_data["trainer"] = trainer_match.group(1).strip()
                    
                    # Save to horses collection
                    self.db.db["horses"].replace_one(
                        {"hkjc_horse_id": horse_id}, 
                        horse_data, 
                        upsert=True
                    )
                    
                    # Extract race URLs from table
                    tables = await page.query_selector_all("table.bigborder")
                    
                    for table in tables:
                        rows = await table.query_selector_all("tr")
                        
                        for row in rows[1:]:
                            cells = await row.query_selector_all("td")
                            if len(cells) < 3:
                                continue
                            
                            # Check for race URL
                            links = await row.query_selector_all("a[href*='localresults']")
                            if not links:
                                continue
                            
                            href = await links[0].get_attribute("href")
                            full_url = "https://racing.hkjc.com" + href
                            
                            # Parse URL
                            date_match = re.search(r'racedate=([^&]+)', href)
                            course_match = re.search(r'Racecourse=([^&]+)', href)
                            no_match = re.search(r'RaceNo=(\d+)', href)
                            
                            if date_match and course_match and no_match:
                                race_key = f"{date_match.group(1)}_{course_match.group(1)}_{no_match.group(1)}"
                                
                                # Extract race data from cells
                                race_data = {
                                    "hkjc_horse_id": horse_id,
                                    "race_no": (await cells[0].inner_text()).strip(),
                                    "position": (await cells[1].inner_text()).strip(),
                                    "date": (await cells[2].inner_text()).strip(),
                                    "venue": (await cells[3].inner_text()).strip(),
                                    "distance": (await cells[4].inner_text()).strip(),
                                    "race_url": full_url,
                                    "race_id": race_key,
                                }
                                
                                # Save race history (check for duplicate)
                                existing = self.db.db["horse_race_history"].find_one({
                                    "hkjc_horse_id": horse_id,
                                    "race_id": race_key
                                })
                                if not existing:
                                    self.db.db["horse_race_history"].insert_one(race_data)
                                
                                if race_key not in race_urls:
                                    race_urls[race_key] = {
                                        "url": full_url,
                                        "race_date": date_match.group(1),
                                        "course": course_match.group(1),
                                        "race_no": int(no_match.group(1)),
                                        "source_horses": []
                                    }
                                
                                race_urls[race_key]["source_horses"].append(horse_id)
                    
                    # Also save race history to MongoDB
                    # (We need to extract full race data, not just URL)
                    
                    print(f"   ✅ {horse_id}: {len(race_urls)} unique races")
                    
                except Exception as e:
                    print(f"   ❌ {horse_id}: {e}")
                    self.stats["errors"].append({"horse": horse_id, "error": str(e)})
                
                finally:
                    await page.close()
        
        # Scrape all horses
        tasks = [scrape_horse(hid) for hid in horse_ids]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        print(f"   ✅ Total unique race URLs: {len(race_urls)}")
        
        return race_urls
    
    async def scrape_races(self, browser, race_urls: Dict):
        """Phase 4: Scrape race results"""
        print("\n📋 PHASE 4: Race Results")
        print("-" * 50)
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_race(race_key: str, race_info: Dict):
            async with semaphore:
                page = await browser.new_page()
                
                try:
                    await page.goto(race_info["url"], wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    
                    text = await page.inner_text("body")
                    
                    # Extract race metadata
                    race_data = {
                        "_id": race_key,
                        "race_date": race_info["race_date"],
                        "racecourse": race_info["course"],
                        "race_no": race_info["race_no"],
                    }
                    
                    # Race ID number
                    race_id_match = re.search(r'第\s*(\d+)\s*場\s*\((\d+)\)', text)
                    if race_id_match:
                        race_data["race_id_num"] = int(race_id_match.group(2))
                    
                    # Distance
                    dist_match = re.search(r'([一二三]級賽|[一二三四五]班)\s*-\s*(\d+)米', text)
                    if dist_match:
                        race_data["class"] = dist_match.group(1)
                        race_data["distance"] = int(dist_match.group(2))
                    
                    # Track condition
                    track_match = re.search(r'場地狀況\s*:\s*(\S+)', text)
                    if track_match:
                        race_data["track_condition"] = track_match.group(1)
                    
                    # Prize
                    prize_match = re.search(r'HK\$\s*([\d,]+)', text)
                    if prize_match:
                        race_data["prize"] = f"HK${prize_match.group(1)}"
                    
                    # Extract results
                    tables = await page.query_selector_all("table.f_tac.table_bd.draggable")
                    results = []
                    
                    for table in tables:
                        rows = await table.query_selector_all("tr")
                        
                        for row in rows[1:]:
                            cells = await row.query_selector_all("td")
                            if len(cells) < 8:
                                continue
                            
                            # Check position
                            pos = (await cells[0].inner_text()).strip()
                            if not pos.isdigit():
                                continue
                            
                            # Horse link
                            link = await cells[2].query_selector("a")
                            horse_id = ""
                            horse_name = ""
                            if link:
                                href = await link.get_attribute("href")
                                mid = re.search(r'horseid=([^&]+)', href or "")
                                if mid:
                                    horse_id = mid.group(1)
                                horse_name = (await link.inner_text()).strip()
                            
                            result = {
                                "race_id": race_key,
                                "position": int(pos),
                                "horse_no": (await cells[1].inner_text()).strip(),
                                "horse_id": horse_id,
                                "horse_name": horse_name,
                                "jockey": (await cells[3].inner_text()).strip(),
                                "trainer": (await cells[4].inner_text()).strip(),
                            }
                            results.append(result)
                    
                    # Save race
                    self.db.db["races"].replace_one({"_id": race_key}, race_data, upsert=True)
                    
                    # Save results
                    self.db.db["race_results"].delete_many({"race_id": race_key})
                    if results:
                        self.db.db["race_results"].insert_many(results)
                    
                    print(f"   ✅ {race_key}: {len(results)} horses")
                    self.stats["races"] += 1
                    
                except Exception as e:
                    print(f"   ❌ {race_key}: {e}")
                    self.stats["errors"].append({"race": race_key, "error": str(e)})
                
                finally:
                    await page.close()
        
        # Scrape all races
        tasks = [scrape_race(k, v) for k, v in race_urls.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def print_summary(self):
        """Print final summary"""
        print("\n" + "=" * 70)
        print("📊 SCRAPING SUMMARY")
        print("=" * 70)
        print(f"👤 Jockeys:    {self.stats['jockeys']}")
        print(f"🏇 Trainers:   {self.stats['trainers']}")
        print(f"🐴 Horses:     {self.stats['horses']}")
        print(f"🏁 Races:      {self.stats['races']}")
        print(f"❌ Errors:      {len(self.stats['errors'])}")
        
        if self.stats["errors"]:
            print("\nErrors:")
            for e in self.stats["errors"][:5]:
                print(f"  - {e}")
        
        print("\n✅ Complete!")


async def main():
    """Entry point"""
    scraper = HKJCCompleteScraper(max_concurrent=2, headless=True)
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
