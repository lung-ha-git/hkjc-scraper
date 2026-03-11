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
import time
from datetime import datetime, timezone
from typing import List, Dict, Set

def get_now():
    """Get current UTC timestamp"""
    return datetime.now(timezone.utc).isoformat()

def add_timestamps(doc: Dict, is_new: bool = True) -> Dict:
    """Add created_at and modified_at timestamps to a document"""
    now = get_now()
    if is_new:
        doc["created_at"] = now
    doc["modified_at"] = now
    return doc
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from src.utils.scraper_activity_log import get_activity_log
from src.utils.scraping_queue import get_scraping_queue, get_race_queue
from playwright.async_api import async_playwright

# Import activity log
try:
    from src.utils.scraper_activity_log import get_activity_log
except ImportError:
    from scraper_activity_log import get_activity_log


class HKJCCompleteScraper:
    """Complete HKJC scraper workflow"""
    
    def __init__(self, max_concurrent: int = 2, headless: bool = True, resume: bool = True):
        self.max_concurrent = max_concurrent
        self.headless = headless
        self.db = None
        self.resume = resume
        self.phase3_only = False  # Will be set by main()
        self.phase4_only = False  # Will be set by main()
        
        # Activity log for tracking progress
        self.activity_log = get_activity_log()
        
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
        
        # Handle phase4_only mode
        if self.phase4_only:
            print("\n🔄 Phase 4 Only Mode - Loading race URLs from database...")
            self.db = DatabaseConnection()
            if not self.db.connect():
                print("❌ Cannot connect to MongoDB")
                return
            
            # Extract race URLs from race_history
            race_urls = {}
            for doc in self.db.db.horse_race_history.find({'race_url': {'$exists': True, '$ne': ''}}):
                race_url = doc.get('race_url', '')
                if race_url and race_url not in race_urls:
                    import re
                    date_match = re.search(r'racedate=(\d+/\d+/\d+)', race_url)
                    course_match = re.search(r'Racecourse=(\w+)', race_url)
                    race_no_match = re.search(r'RaceNo=(\d+)', race_url)
                    
                    if date_match and course_match and race_no_match:
                        race_key = f"{date_match.group(1).replace('/', '_')}_{course_match.group(1)}_{race_no_match.group(1)}"
                        race_urls[race_key] = {
                            'url': race_url,
                            'race_date': date_match.group(1),
                            'course': course_match.group(1),
                            'race_no': race_no_match.group(1)
                        }
            
            print(f"   📋 Found {len(race_urls)} races from race_history")
            
            # Initialize race queue
            race_queue = get_race_queue()
            race_queue.connect()
            race_queue.init_queue(list(race_urls.keys()))
            
            # Run Phase 4
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                try:
                    await self.scrape_races(browser, race_urls)
                finally:
                    await browser.close()
            
            self.db.disconnect()
            print("\n✅ Phase 4 Complete!")
            return
        
        # Show current progress
        print("\n📊 Current Progress:")
        self.activity_log.print_summary()
        
        # Check if we should resume
        if self.resume:
            processed_horses = self.activity_log.get_processed_horses("horse_detail")
            if processed_horses:
                print(f"\n🔄 Resume mode: {len(processed_horses)} horses already processed")
        
        # Connect to DB
        self.db = DatabaseConnection()
        if not self.db.connect():
            print("❌ Cannot connect to MongoDB")
            return
        
        # Log workflow start
        self.activity_log.log_start("workflow", race_id="main")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            
            try:
                # Phase 1: Jockeys & Trainers
                self.activity_log.log_start("phase1_jockeys_trainers")
                await self.scrape_jockeys_trainers(browser)
                self.activity_log.log_complete("phase1_jockeys_trainers")
                
                # Phase 2: Horse List (二字馬)
                self.activity_log.log_start("phase2_horse_list")
                horse_ids = await self.scrape_horse_list(browser)
                self.activity_log.log_complete("phase2_horse_list", records_count=len(horse_ids))
                
                # Initialize scraping queue
                queue = get_scraping_queue()
                queue.connect()
                queue.init_queue(horse_ids)
                print(f"   📋 Initialized scraping queue with {len(horse_ids)} horses")
                
                # Phase 3: Horse Details + Race URLs
                self.activity_log.log_start("phase3_horse_detail")
                race_urls = await self.scrape_horses_details(browser, horse_ids)
                self.activity_log.log_complete("phase3_horse_detail", records_count=len(race_urls))
                
                # Phase 4: Race Results (skip if phase3_only)
                if not self.phase3_only:
                    self.activity_log.log_start("phase4_race_results")
                    
                    # Initialize race queue
                    race_queue = get_race_queue()
                    race_queue.connect()
                    race_queue.init_queue(list(race_urls.keys()))
                    print(f"   📋 Initialized race queue with {len(race_urls)} races")
                    
                    await self.scrape_races(browser, race_urls)
                    
                    # Print race queue stats
                    race_stats = race_queue.get_stats()
                    print(f"   📋 Race queue stats: {race_stats}")
                    
                    self.activity_log.log_complete("phase4_race_results", records_count=len(race_urls))
                else:
                    print("\n⏭️  Phase 4 skipped (--phase3-only mode)")
                
                # Log workflow complete
                self.activity_log.log_complete("workflow")
                
            finally:
                await browser.close()
        
        self.db.disconnect()
        
        # Print summary
        self.print_summary()
        
        # Final activity log summary
        self.activity_log.print_summary()
    
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
        
        # Go to selecthorse pages - get ALL horses (2/3/4字馬)
        print("🔍 Getting ALL horses from HKJC (2/3/4字馬)...")
        
        horse_ids = []
        seen = set()
        
        # Use dedicated URLs for 2/3/4字馬
        for ordertype in [2, 3, 4]:
            try:
                url = f"https://racing.hkjc.com/zh-hk/local/information/selecthorsebychar?ordertype={ordertype}"
                await page.goto(url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                
                # Get all horse links
                links = await page.query_selector_all("a[href*='horse?horseid=']")
                
                count = 0
                for link in links:
                    href = await link.get_attribute("href")
                    match = re.search(r'horseid=(HK_\d+_[A-Z]\d+)', href or "")
                    
                    if match:
                        horse_id = match.group(1)
                        if horse_id not in seen:
                            seen.add(horse_id)
                            horse_ids.append(horse_id)
                            count += 1
                
                print(f"   {ordertype}字馬: {count} horses")
            except Exception as e:
                print(f"   Error with {ordertype}字馬: {e}")
        
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
                # Mark horse as in progress
                try:
                    queue = get_scraping_queue()
                    queue.connect()
                    queue.mark_in_progress(horse_id)
                except:
                    pass
                
                page = await browser.new_page()
                
                try:
                    url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}"
                    await page.goto(url, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    
                    text = await page.inner_text("body")
                    title = await page.title()
                    
                    # Extract comprehensive horse info
                    horse_data = {"hkjc_horse_id": horse_id}
                    
                    # Extract horse_code (烙號) from hkjc_horse_id for jersey URL
                    # e.g., HK_2024_K305 -> K305
                    parts = horse_id.split("_")
                    if len(parts) >= 3:
                        horse_code = parts[2]  # e.g., K305
                        horse_data["horse_code"] = horse_code
                        horse_data["jersey_url"] = f"https://racing.hkjc.com/racing/content/Images/RaceColor/{horse_code}.gif"
                    
                    # Name - get from page title
                    # Title format: "馬名 - 馬匹資料 - 賽馬資訊 - 香港賽馬會"
                    title_match = re.search(r'^([^-]+)', title)
                    if title_match:
                        horse_data["name"] = title_match.group(1).strip()
                    
                    # 出生地 / 馬齡 (Country of origin / Age)
                    # Example: "紐西蘭 / 5"
                    origin_age_match = re.search(r'出生地\s*/\s*馬齡\s*[:：]\s*([^\s/]+)\s*/\s*(\d+)', text)
                    if origin_age_match:
                        horse_data["country_of_origin"] = origin_age_match.group(1).strip()
                        horse_data["age"] = int(origin_age_match.group(2).strip())
                    
                    # 毛色 / 性別 (Color / Sex)
                    # Example: "棗 / 閹"
                    color_sex_match = re.search(r'毛色\s*/\s*性別\s*[:：]\s*([^\s/]+)\s*/\s*(\S+)', text)
                    if color_sex_match:
                        horse_data["color"] = color_sex_match.group(1).strip()
                        horse_data["sex"] = color_sex_match.group(2).strip()
                    
                    # 進口類別 (Import type)
                    import_type_match = re.search(r'進口類別\s*[:：]\s*([^\n]+)', text)
                    if import_type_match:
                        horse_data["import_type"] = import_type_match.group(1).strip()
                    
                    # 今季獎金 (Season prize)
                    # Example: "$7,786,500" -> 7786500
                    season_prize_match = re.search(r'今季獎金.*?:\s*\$?([\d,]+)', text)
                    if season_prize_match:
                        horse_data["season_prize"] = int(season_prize_match.group(1).replace(',', ''))
                    
                    # 總獎金 (Total prize)
                    total_prize_match = re.search(r'總獎金.*?:\s*\$?([\d,]+)', text)
                    if total_prize_match:
                        horse_data["total_prize"] = int(total_prize_match.group(1).replace(',', ''))
                    
                    # 冠-亞-季-總出賽次數 (Wins-Seconds-Thirds-Total starts)
                    # Example: "6-3-2-17"
                    career_match = re.search(r'冠-亞-季-總出賽次數.*?(\d+)-(\d+)-(\d+)-(\d+)', text)
                    if career_match:
                        horse_data["career_wins"] = int(career_match.group(1))
                        horse_data["career_seconds"] = int(career_match.group(2))
                        horse_data["career_thirds"] = int(career_match.group(3))
                        horse_data["career_starts"] = int(career_match.group(4))
                    
                    # 最近十個賽馬日 出賽場數 (Runs in last 10 race days)
                    recent_runs_match = re.search(r'最近十個賽馬日\s*出賽場數\s*[:：]\s*(\d+)', text)
                    if recent_runs_match:
                        horse_data["recent_10_race_days_runs"] = int(recent_runs_match.group(1))
                    
                    # 現在位置 (到達日期) (Current location (arrival date))
                    # Example: "香港 (10/01/2026)"
                    location_match = re.search(r'現在位置.*?\(到達日期\).*?([^\s(]+)\s*\((\d{2}/\d{2}/\d{2,4})\)', text)
                    if location_match:
                        horse_data["current_location"] = location_match.group(1).strip()
                        horse_data["arrival_date"] = location_match.group(2).strip()
                    
                    # 進口日期 (Import date)
                    import_date_match = re.search(r'進口日期\s*[:：]\s*(\d{2}/\d{2}/\d{2,4})', text)
                    if import_date_match:
                        horse_data["import_date"] = import_date_match.group(1).strip()
                    
                    # 練馬師 (Trainer)
                    trainer_match = re.search(r'練馬師\s*[:：]\s*([^\n]+)', text)
                    if trainer_match:
                        trainer_text = trainer_match.group(1).strip()
                        # Remove any links
                        trainer_text = re.sub(r'\[.*?\]', '', trainer_text).strip()
                        horse_data["trainer"] = trainer_text
                    
                    # 馬主 (Horse owner)
                    owner_match = re.search(r'馬主\s*[:：]\s*([^\n]+)', text)
                    if owner_match:
                        owner_text = owner_match.group(1).strip()
                        owner_text = re.sub(r'\[.*?\]', '', owner_text).strip()
                        horse_data["owner"] = owner_text
                    
                    # 現時評分 (Current rating)
                    current_rating_match = re.search(r'現時評分\s*[:：]\s*(\d+)', text)
                    if current_rating_match:
                        horse_data["current_rating"] = int(current_rating_match.group(1))
                    
                    # 季初評分 (Season start rating)
                    season_start_rating_match = re.search(r'季初評分\s*[:：]\s*(\d+)', text)
                    if season_start_rating_match:
                        horse_data["season_start_rating"] = int(season_start_rating_match.group(1))
                    
                    # 父系 (Sire)
                    sire_match = re.search(r'父系\s*[:：]\s*([^\n]+)', text)
                    if sire_match:
                        sire_text = sire_match.group(1).strip()
                        sire_text = re.sub(r'\[.*?\]', '', sire_text).strip()
                        horse_data["sire"] = sire_text
                    
                    # 母系 (Dam)
                    dam_match = re.search(r'母系\s*[:：]\s*([^\n]+)', text)
                    if dam_match:
                        dam_text = dam_match.group(1).strip()
                        dam_text = re.sub(r'\[.*?\]', '', dam_text).strip()
                        horse_data["dam"] = dam_text
                    
                    # 外祖父 (Maternal grand sire)
                    mgs_match = re.search(r'外祖父\s*[:：]\s*([^\n]+)', text)
                    if mgs_match:
                        mgs_text = mgs_match.group(1).strip()
                        mgs_text = re.sub(r'\[.*?\]', '', mgs_text).strip()
                        horse_data["maternal_grand_sire"] = mgs_text
                    
                    # Save to horses collection
                    horse_data = add_timestamps(horse_data)
                    self.db.db["horses"].replace_one(
                        {"hkjc_horse_id": horse_id}, 
                        horse_data, 
                        upsert=True
                    )
                    
                    self.stats["horses"] += 1
                    
                    # Log successful horse scrape
                    self.activity_log.log_complete(
                        phase="horse_detail",
                        horse_id=horse_id,
                        records_count=len(race_urls)
                    )
                    
                    # Update scraping queue with data counts (will re-count from actual collections)
                    try:
                        queue = get_scraping_queue()
                        queue.connect()
                        # Don't pass data_counts - let it re-count from collections
                        queue.update_data_status(horse_id)
                    except Exception as e:
                        print(f"   ⚠️  Queue update failed: {e}")
                    
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
                            # Use correct URL format for race results
                            if "localresults" in href:
                                full_url = "https://racing.hkjc.com" + href
                            else:
                                full_url = "https://racing.hkjc.com" + href
                            
                            # Parse URL
                            date_match = re.search(r'racedate=([^&]+)', href)
                            course_match = re.search(r'Racecourse=([^&]+)', href)
                            no_match = re.search(r'RaceNo=(\d+)', href)
                            
                            if date_match and course_match and no_match:
                                race_key = f"{date_match.group(1)}_{course_match.group(1)}_{no_match.group(1)}"
                                
                                # Extract ALL race data from cells
                                # Columns: 場次, 名次, 日期, 馬場/跑道/賽道, 途程, 場地狀況, 賽事班次, 檔位, 評分, 練馬師, 騎師, 頭馬距離, 獨贏賠率, 實際負磅, 沿途走位, 完成時間, 排位體重, 配備
                                race_data = {
                                    "hkjc_horse_id": horse_id,
                                    "race_no": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                    "position": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                    "date": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                                    "venue": (await cells[3].inner_text()).strip() if len(cells) > 3 else "",
                                    "distance": (await cells[4].inner_text()).strip() if len(cells) > 4 else "",
                                    "track_condition": (await cells[5].inner_text()).strip() if len(cells) > 5 else "",
                                    "race_class": (await cells[6].inner_text()).strip() if len(cells) > 6 else "",
                                    "draw": (await cells[7].inner_text()).strip() if len(cells) > 7 else "",
                                    "rating": (await cells[8].inner_text()).strip() if len(cells) > 8 else "",
                                    "trainer": (await cells[9].inner_text()).strip() if len(cells) > 9 else "",
                                    "jockey": (await cells[10].inner_text()).strip() if len(cells) > 10 else "",
                                    "distance_behind": (await cells[11].inner_text()).strip() if len(cells) > 11 else "",
                                    "odds": (await cells[12].inner_text()).strip() if len(cells) > 12 else "",
                                    "weight": (await cells[13].inner_text()).strip() if len(cells) > 13 else "",
                                    "running_position": (await cells[14].inner_text()).strip() if len(cells) > 14 else "",
                                    "finish_time": (await cells[15].inner_text()).strip() if len(cells) > 15 else "",
                                    "draw_weight": (await cells[16].inner_text()).strip() if len(cells) > 16 else "",
                                    "gear": (await cells[17].inner_text()).strip() if len(cells) > 17 else "",
                                    "race_url": full_url,
                                    "race_id": race_key,
                                }
                                
                                # Save race history (check for duplicate)
                                existing = self.db.db["horse_race_history"].find_one({
                                    "hkjc_horse_id": horse_id,
                                    "race_id": race_key
                                })
                                if not existing:
                                    race_data = add_timestamps(race_data)
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
                    
                    # Task 1: 馬匹評分/體重/名次 - NEW FORMAT
                    try:
                        rating_url = f"https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid={horse_id}"
                        await page.goto(rating_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        # Parse the rating table
                        tables = await page.query_selector_all("table")
                        
                        rating_records = []
                        
                        rating_records = []
                        
                        for table in tables:
                            rows = await table.query_selector_all("tr")
                            if len(rows) < 10:
                                continue
                            
                            # Check if this is the rating table - look at row 2 for "評分"
                            # Row structure: row 0=name, row 1=dates, row 2=ratings, row 3=results, etc.
                            if len(rows) > 2:
                                row2_text = await rows[2].inner_text()
                                if "評分" not in row2_text:
                                    continue
                            else:
                                continue
                            
                            # Get number of columns (must have more than 1 to have data)
                            first_data_row = await rows[1].query_selector_all("td")
                            num_cols = len(first_data_row)
                            if num_cols <= 1:
                                continue  # Skip tables without data
                            
                            # Extract columns (each column is a race, each row is a field)
                            # Row 1: dates, Row 2: ratings, Row 3: results, Row 4: weights
                            # Row 5: venue, Row 6: track_type, Row 7: distance, Row 8: course
                            # Row 9: track_condition, Row 10: race_class
                            
                            for col_idx in range(1, num_cols):  # Skip first column (headers)
                                try:
                                    date = (await first_data_row[col_idx].inner_text()).strip() if col_idx < len(first_data_row) else ""
                                    if not date:
                                        continue
                                    
                                    # Extract all fields for this column
                                    rating_cells = await rows[2].query_selector_all("td")
                                    result_cells = await rows[3].query_selector_all("td")
                                    weight_cells = await rows[4].query_selector_all("td")
                                    venue_cells = await rows[5].query_selector_all("td")
                                    track_type_cells = await rows[6].query_selector_all("td")
                                    distance_cells = await rows[7].query_selector_all("td")
                                    course_cells = await rows[8].query_selector_all("td")
                                    condition_cells = await rows[9].query_selector_all("td")
                                    class_cells = await rows[10].query_selector_all("td")
                                    
                                    # Parse date format: "11/02/2026" -> "2026-02-11"
                                    date_parts = date.split("/")
                                    if len(date_parts) == 3:
                                        formatted_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                                    else:
                                        formatted_date = date
                                    
                                    # Parse distance (remove any non-numeric)
                                    distance_str = (await distance_cells[col_idx].inner_text()).strip() if col_idx < len(distance_cells) else "0"
                                    try:
                                        distance = int(distance_str)
                                    except:
                                        distance = 0
                                    
                                    # Parse race class
                                    class_str = (await class_cells[col_idx].inner_text()).strip() if col_idx < len(class_cells) else ""
                                    try:
                                        race_class = int(class_str)
                                    except:
                                        race_class = 0
                                    
                                    # Parse horse weight
                                    weight_str = (await weight_cells[col_idx].inner_text()).strip() if col_idx < len(weight_cells) else "0"
                                    try:
                                        horse_weight = int(weight_str)
                                    except:
                                        horse_weight = 0
                                    
                                    # Parse rating
                                    rating_str = (await rating_cells[col_idx].inner_text()).strip() if col_idx < len(rating_cells) else "0"
                                    try:
                                        rating = int(rating_str)
                                    except:
                                        rating = 0
                                    
                                    record = {
                                        "hkjc_horse_id": horse_id,
                                        "date": formatted_date,
                                        "rating": rating,
                                        "result": (await result_cells[col_idx].inner_text()).strip() if col_idx < len(result_cells) else "",
                                        "horse_weight": horse_weight,
                                        "venue": (await venue_cells[col_idx].inner_text()).strip() if col_idx < len(venue_cells) else "",
                                        "track_type": (await track_type_cells[col_idx].inner_text()).strip() if col_idx < len(track_type_cells) else "",
                                        "distance": distance,
                                        "course": (await course_cells[col_idx].inner_text()).strip() if col_idx < len(course_cells) else "",
                                        "track_condition": (await condition_cells[col_idx].inner_text()).strip() if col_idx < len(condition_cells) else "",
                                        "race_class": race_class
                                    }
                                    
                                    rating_records.append(record)
                                except Exception as e:
                                    continue
                            
                            break  # Found the table, no need to check others
                        
                        # Save to horse_ratings collection (one document per record)
                        if rating_records:
                            # Delete old records
                            self.db.db["horse_ratings"].delete_many({"hkjc_horse_id": horse_id})
                            # Insert new records
                            self.db.db["horse_ratings"].insert_many(rating_records)
                            print(f"      ✅ horse_ratings: {len(rating_records)} records")
                    except Exception as e:
                        print(f"      ⚠️  horse_ratings failed: {e}")
                    
                    # Task 2: 所跑途程賽績紀錄 - Using direct performance URL
                    # (kept for reference, can be removed later)
                    try:
                        perf_url = f"https://racing.hkjc.com/zh-hk/local/information/performance?horseid={horse_id}"
                        await page.goto(perf_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        # Initialize structure - NEW FORMAT
                        dist_perf = {
                            "hkjc_horse_id": horse_id,
                            "track_performance": [],
                            "distance_performance": {},
                            "seasonal_performance": [],
                            "overall_total": {}
                        }
                        
                        # Track current venue for distance performance
                        current_venue = None  # shatin_turf, shatin_awt, happy_valley_turf
                        
                        # Find performance table
                        tables = await page.query_selector_all("table.horseperformance")
                        
                        for table in tables:
                            rows = await table.query_selector_all("tr")
                            
                            current_section = ''
                            current_dist = ''
                            
                            for row in rows:
                                cells = await row.query_selector_all("td")
                                cell_texts = [(await c.inner_text()).strip() for c in cells]
                                
                                if not cell_texts:
                                    continue
                                
                                # Check for section headers
                                if cell_texts[0] == '場地成績':
                                    current_section = 'track'
                                    continue
                                elif cell_texts[0] == '路程成績':
                                    current_section = 'distance'
                                    current_venue = None
                                    continue
                                elif cell_texts[0] == '歷季成績':
                                    current_section = 'season'
                                    continue
                                
                                # Skip summary rows
                                if any(x in cell_texts[1] for x in ['總成績', '總']):
                                    continue
                                
                                # Parse track performance (場地成績)
                                if current_section == 'track':
                                    surface = cell_texts[0] if cell_texts[0] else ""
                                    condition = cell_texts[1] if len(cell_texts) > 1 else ""
                                    
                                    if not surface or "總" in surface:
                                        continue
                                    
                                    # Determine surface type
                                    surface_type = "草地" if "草" in surface else "全天候跑道"
                                    
                                    dist_perf["track_performance"].append({
                                        "surface": surface_type,
                                        "condition": condition,
                                        "starts": int(cell_texts[2]) if cell_texts[2].isdigit() else 0,
                                        "win": int(cell_texts[3]) if cell_texts[3].isdigit() else 0,
                                        "2nd": int(cell_texts[4]) if cell_texts[4].isdigit() else 0,
                                        "3rd": int(cell_texts[5]) if len(cell_texts) > 5 and cell_texts[5].isdigit() else 0,
                                        "unplaced": int(cell_texts[6]) if len(cell_texts) > 6 and cell_texts[6].isdigit() else 0
                                    })
                                
                                # Parse distance performance (路程成績) - NEW FORMAT
                                elif current_section == 'distance':
                                    first_text = cell_texts[0].strip() if cell_texts[0] else ""
                                    
                                    # Check for venue headers (沙田馬場, 跑馬地馬場)
                                    if "沙田" in first_text:
                                        if "草地" in first_text:
                                            current_venue = "shatin_turf"
                                        else:
                                            current_venue = "shatin_awt"
                                        continue
                                    elif "跑馬地" in first_text:
                                        current_venue = "happy_valley_turf"
                                        continue
                                    
                                    if current_venue and first_text:
                                        distance = first_text
                                        
                                        # Check for total row (總成績)
                                        if "總" in first_text or "合計" in first_text:
                                            dist_perf["distance_performance"][f"{current_venue}_total"] = {
                                                "starts": int(cell_texts[1]) if len(cell_texts) > 1 and cell_texts[1].isdigit() else 0,
                                                "win": int(cell_texts[2]) if len(cell_texts) > 2 and cell_texts[2].isdigit() else 0,
                                                "2nd": int(cell_texts[3]) if len(cell_texts) > 3 and cell_texts[3].isdigit() else 0,
                                                "3rd": int(cell_texts[4]) if len(cell_texts) > 4 and cell_texts[4].isdigit() else 0,
                                                "unplaced": int(cell_texts[5]) if len(cell_texts) > 5 and cell_texts[5].isdigit() else 0
                                            }
                                        else:
                                            # Individual distance record
                                            if current_venue not in dist_perf["distance_performance"]:
                                                dist_perf["distance_performance"][current_venue] = []
                                            
                                            dist_perf["distance_performance"][current_venue].append({
                                                "distance": distance,
                                                "starts": int(cell_texts[1]) if len(cell_texts) > 1 and cell_texts[1].isdigit() else 0,
                                                "win": int(cell_texts[2]) if len(cell_texts) > 2 and cell_texts[2].isdigit() else 0,
                                                "2nd": int(cell_texts[3]) if len(cell_texts) > 3 and cell_texts[3].isdigit() else 0,
                                                "3rd": int(cell_texts[4]) if len(cell_texts) > 4 and cell_texts[4].isdigit() else 0,
                                                "unplaced": int(cell_texts[5]) if len(cell_texts) > 5 and cell_texts[5].isdigit() else 0
                                            })
                                
                                # Parse seasonal performance (歷季成績)
                                elif current_section == 'season':
                                    if len(cell_texts) >= 5 and cell_texts[1] not in ['總成績']:
                                        dist_perf["seasonal_performance"].append({
                                            "season": cell_texts[1],
                                            "starts": int(cell_texts[2]) if cell_texts[2].isdigit() else 0,
                                            "win": int(cell_texts[3]) if cell_texts[3].isdigit() else 0,
                                            "2nd": int(cell_texts[4]) if cell_texts[4].isdigit() else 0,
                                            "3rd": int(cell_texts[5]) if len(cell_texts) > 5 and cell_texts[5].isdigit() else 0,
                                            "unplaced": int(cell_texts[6]) if len(cell_texts) > 6 and cell_texts[6].isdigit() else 0
                                        })
                        
                        # Calculate overall_total from track performance
                        total_starts = sum(t.get("starts", 0) for t in dist_perf["track_performance"])
                        total_wins = sum(t.get("win", 0) for t in dist_perf["track_performance"])
                        total_2nd = sum(t.get("2nd", 0) for t in dist_perf["track_performance"])
                        total_3rd = sum(t.get("3rd", 0) for t in dist_perf["track_performance"])
                        total_unplaced = sum(t.get("unplaced", 0) for t in dist_perf["track_performance"])
                        
                        dist_perf["overall_total"] = {
                            "starts": total_starts,
                            "win": total_wins,
                            "2nd": total_2nd,
                            "3rd": total_3rd,
                            "unplaced": total_unplaced
                        }
                        
                        # Save
                        existing = self.db.db["horse_distance_stats"].find_one({
                            "hkjc_horse_id": horse_id
                        })
                        if not existing and (dist_perf["track_performance"] or dist_perf["distance_performance"]):
                            dist_perf = add_timestamps(dist_perf)
                            self.db.db["horse_distance_stats"].insert_one(dist_perf)
                    except Exception as e:
                        pass
                    
                    # Task 3: 晨操紀錄 - Use dedicated trackworkresult URL
                    try:
                        # Use dedicated trackworkresult URL
                        workouts_url = f"https://racing.hkjc.com/zh-hk/local/information/trackworkresult?horseid={horse_id}"
                        await page.goto(workouts_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        tables = await page.query_selector_all("table")
                        
                        workout_count = 0
                        for table in tables:
                            table_class = await table.get_attribute("class") or ""
                            
                            # STRICT: Only use table with class "table_bd f_tal f_fs13 f_ffChinese"
                            if "table_bd" not in table_class or "f_tal" not in table_class:
                                continue
                            
                            rows = await table.query_selector_all("tr")
                            if len(rows) < 2:
                                continue
                            
                            # Verify header
                            header = await rows[0].inner_text()
                            if "日期" not in header or "晨操" not in header:
                                continue
                            
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 2:
                                    date_text = (await cells[0].inner_text()).strip()
                                    
                                    # Skip empty/invalid rows
                                    if not date_text or date_text in ['日期', 'None', '']:
                                        continue
                                    
                                    workout = {
                                        "hkjc_horse_id": horse_id,
                                        "date": date_text,
                                        "workout_type": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                        "venue": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                                        "details": (await cells[3].inner_text()).strip() if len(cells) > 3 else "",
                                        "gear": (await cells[4].inner_text()).strip() if len(cells) > 4 else "",
                                    }
                                    
                                    if workout.get("date"):
                                        workout = add_timestamps(workout)
                                        self.db.db["horse_workouts"].insert_one(workout)
                                        workout_count += 1
                            
                            if workout_count > 0:
                                print(f"      📝 Workouts: {workout_count}")
                                break
                    except Exception as e:
                        pass  # Silent fail
                    
                    # Task 4: 傷患紀錄 - Use ovehorse URL with table_bd class
                    try:
                        # Use ovehorse URL
                        medical_url = f"https://racing.hkjc.com/zh-hk/local/information/ovehorse?horseid={horse_id}"
                        await page.goto(medical_url, wait_until="networkidle")
                        await asyncio.sleep(2)
                        
                        tables = await page.query_selector_all("table")
                        
                        medical_count = 0
                        for table in tables:
                            table_class = await table.get_attribute("class") or ""
                            rows = await table.query_selector_all("tr")
                            
                            # Must use table class "table_bd"
                            if "table_bd" not in table_class:
                                continue
                            
                            if len(rows) < 2:
                                continue
                            
                            header = await rows[0].inner_text()
                            
                            # Must have medical columns: 日期, 詳情, 通過日期
                            if "日期" not in header or "詳情" not in header:
                                continue
                            
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 3:
                                    date_text = (await cells[0].inner_text()).strip()
                                    
                                    # Skip header rows
                                    if not date_text or date_text in ["日期", "None", ""]:
                                        continue
                                    
                                    med = {
                                        "hkjc_horse_id": horse_id,
                                        "date": date_text,
                                        "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                        "pass_date": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                                    }
                                    
                                    if med.get("date"):
                                        med = add_timestamps(med)
                                        self.db.db["horse_medical"].insert_one(med)
                                        medical_count += 1
                            
                            if medical_count > 0:
                                print(f"      🏥 Medical: {medical_count}")
                                break
                    
                    except Exception as e:
                        pass  # Silent fail
                    
                    # Task 5: 搬遷紀錄 - Use direct movementrecords URL
                    try:
                        # Use dedicated movementrecords URL
                        movement_url = f"https://racing.hkjc.com/zh-hk/local/information/movementrecords?horseid={horse_id}"
                        await page.goto(movement_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        tables = await page.query_selector_all("table")
                        
                        move_count = 0
                        for table in tables:
                            table_id = await table.get_attribute("id") or ""
                            
                            # STRICT: Only use MovementRecord table
                            if "MovementRecord" not in table_id:
                                continue
                            
                            rows = await table.query_selector_all("tr")
                            if len(rows) < 2:
                                continue
                            
                            header = await rows[0].inner_text()
                            # Verify it's the right table with 從, 至, 到達日期 columns
                            if "從" not in header or "至" not in header or "到達日期" not in header:
                                continue
                            
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 3:
                                    cell_texts = [(await c.inner_text()).strip() for c in cells]
                                    
                                    from_loc = cell_texts[0] if len(cell_texts) > 0 else ""
                                    to_loc = cell_texts[1] if len(cell_texts) > 1 else ""
                                    arrival_date = cell_texts[2] if len(cell_texts) > 2 else ""
                                    
                                    # Skip empty/None/header rows
                                    if from_loc in ["None", "none", ""] and to_loc in ["None", "none", ""]:
                                        continue
                                    if "從" in from_loc or "至" in from_loc or "從" in to_loc or "至" in to_loc:
                                        continue
                                    if arrival_date in ["None", "none", ""]:
                                        continue
                                    
                                    move = {
                                        "hkjc_horse_id": horse_id,
                                        "from_location": from_loc,
                                        "to_location": to_loc,
                                        "arrival_date": arrival_date
                                    }
                                    if move.get("from_location") or move.get("to_location"):
                                        move = add_timestamps(move)
                                        self.db.db["horse_movements"].insert_one(move)
                                        move_count += 1
                            
                            if move_count > 0:
                                print(f"      📦 Movements: {move_count}")
                                break
                    except Exception as e:
                        pass  # Silent fail
                    
                    # Task 6: 血統簡評
                    try:
                        await page.click("text=血統簡評", timeout=3000)
                        await asyncio.sleep(2)
                        
                        tables = await page.query_selector_all("table.blood")
                        
                        for idx, table in enumerate(tables):
                            rows = await table.query_selector_all("tr")
                            
                            for row in rows:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 2:
                                    pedigree = {
                                        "hkjc_horse_id": horse_id,
                                        "table_idx": idx,
                                        "sire": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                        "dam": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                    }
                                    
                                    if pedigree.get("sire"):
                                        pedigree = add_timestamps(pedigree)
                                        self.db.db["horse_pedigree"].insert_one(pedigree)
                    except:
                        pass
                    
                    print(f"   ✅ {horse_id}: {len(race_urls)} unique races")
                    
                except Exception as e:
                    print(f"   ❌ {horse_id}: {e}")
                    self.stats["errors"].append({"horse": horse_id, "error": str(e)})
                
                finally:
                    await page.close()
        
        # Scrape all horses (with resume support)
        if self.resume:
            processed = self.activity_log.get_processed_horses("horse_detail")
            horses_to_scrape = [h for h in horse_ids if h not in processed]
            skipped = len(horse_ids) - len(horses_to_scrape)
            if skipped > 0:
                print(f"   ⏭️  Skipping {skipped} already processed horses (resume mode)")
        else:
            horses_to_scrape = horse_ids
        
        tasks = [scrape_horse(hid) for hid in horses_to_scrape]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update queue with final stats
        queue = get_scraping_queue()
        queue.connect()
        queue_stats = queue.get_stats()
        print(f"   📋 Queue stats: {queue_stats}")
        
        print(f"   ✅ Total unique race URLs: {len(race_urls)}")
        
        return race_urls
    
    async def scrape_races(self, browser, race_urls: Dict):
        """Phase 4: Scrape race results - MERGED FORMAT"""
        print("\n📋 PHASE 4: Race Results (Merged)")
        print("-" * 50)
        
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        async def scrape_race(race_key: str, race_info: Dict):
            async with semaphore:
                # Mark race as in progress
                try:
                    race_queue = get_race_queue()
                    race_queue.connect()
                    race_queue.mark_in_progress(race_key)
                except:
                    pass
                
                page = await browser.new_page()
                
                try:
                    # Use domcontentloaded for faster initial load, then wait
                    await page.goto(race_info["url"], wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    
                    # Wait for tables to load
                    await page.wait_for_selector("table.f_tac", timeout=10000)
                    
                    text = await page.inner_text("body")
                    
                    # Build merged race document
                    race_data = {
                        "hkjc_race_id": race_key,
                        "race_date": race_info["race_date"],
                        "venue": race_info["course"],
                        "race_no": race_info["race_no"],
                    }
                    
                    # Race ID number
                    race_id_match = re.search(r'第\s*(\d+)\s*場\s*\((\d+)\)', text)
                    if race_id_match:
                        race_data["race_id_num"] = int(race_id_match.group(2))
                    
                    # Distance and class
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
                    
                    # ========== Extract RESULTS ==========
                    tables = await page.query_selector_all("table")
                    results = []
                    
                    for table in tables:
                        class_name = await table.get_attribute("class") or ""
                        if "f_tac" not in class_name:
                            continue
                        
                        rows = await table.query_selector_all("tr")
                        if len(rows) < 3:
                            continue
                        
                        # Check if this is the results table (has 馬號 column)
                        header_cells = await rows[0].query_selector_all("th, td")
                        headers = [(await h.inner_text()).strip() for h in header_cells]
                        
                        if "馬號" not in headers and "名次" not in headers:
                            continue
                        
                        # Find column indices
                        col_idx = {}
                        for i, h in enumerate(headers):
                            h_clean = h.strip()
                            if "馬號" in h_clean:
                                col_idx["horse_number"] = i
                            elif "馬名" in h_clean:
                                col_idx["horse_name"] = i
                            elif "名次" in h_clean:
                                col_idx["rank"] = i
                            elif "練馬師" in h_clean:
                                col_idx["trainer"] = i
                            elif "實際負磅" in h_clean:
                                col_idx["actual_weight"] = i
                            elif "體重" in h_clean:
                                col_idx["declared_weight"] = i
                            elif "獨贏" in h_clean:
                                col_idx["win_odds"] = i
                            elif "騎師" in h_clean:
                                col_idx["jockey"] = i
                            elif "檔位" in h_clean:
                                col_idx["draw"] = i
                            elif "頭馬距離" in h_clean:
                                col_idx["finish_distance"] = i
                            elif "沿途走位" in h_clean:
                                col_idx["running_position"] = i
                            elif "完成時間" in h_clean:
                                col_idx["finish_time"] = i
                        
                        # Extract data rows
                        for row in rows[1:]:
                            cells = await row.query_selector_all("td")
                            if len(cells) < 5:
                                continue
                            
                            cell_texts = [(await c.inner_text()).strip() for c in cells]
                            
                            # Check position/rank
                            rank = cell_texts[col_idx.get("rank", 0)] if col_idx.get("rank", 0) < len(cell_texts) else ""
                            if not rank or not rank.isdigit():
                                continue
                            
                            # Extract horse_id from link
                            horse_id = ""
                            horse_name = ""
                            if col_idx.get("horse_name") and col_idx["horse_name"] < len(cells):
                                link = await cells[col_idx["horse_name"]].query_selector("a")
                                if link:
                                    href = await link.get_attribute("href")
                                    mid = re.search(r'horseid=([^&]+)', href or "")
                                    if mid:
                                        horse_id = mid.group(1)
                                    horse_name = (await link.inner_text()).strip()
                            
                            result = {
                                "horse_number": int(cell_texts[col_idx.get("horse_number", 1)]) if col_idx.get("horse_number") and col_idx["horse_number"] < len(cell_texts) and cell_texts[col_idx["horse_number"]].isdigit() else 0,
                                "horse_name": horse_name,
                                "rank": int(rank),
                                "trainer": cell_texts[col_idx.get("trainer", 4)] if col_idx.get("trainer") and col_idx["trainer"] < len(cell_texts) else "",
                                "actual_weight": int(cell_texts[col_idx.get("actual_weight", 6)]) if col_idx.get("actual_weight") and col_idx["actual_weight"] < len(cell_texts) and cell_texts[col_idx["actual_weight"]].isdigit() else 0,
                                "declared_weight": int(cell_texts[col_idx.get("declared_weight", 5)]) if col_idx.get("declared_weight") and col_idx["declared_weight"] < len(cell_texts) and cell_texts[col_idx["declared_weight"]].isdigit() else 0,
                                "win_odds": float(cell_texts[col_idx.get("win_odds", 7)]) if col_idx.get("win_odds") and col_idx["win_odds"] < len(cell_texts) else 0.0,
                                "jockey": cell_texts[col_idx.get("jockey", 3)] if col_idx.get("jockey") and col_idx["jockey"] < len(cell_texts) else "",
                                "draw": int(cell_texts[col_idx.get("draw", 8)]) if col_idx.get("draw") and col_idx["draw"] < len(cell_texts) and cell_texts[col_idx["draw"]].isdigit() else 0,
                                "finish_distance": cell_texts[col_idx.get("finish_distance", 11)] if col_idx.get("finish_distance") and col_idx["finish_distance"] < len(cell_texts) else "-",
                                "running_position": cell_texts[col_idx.get("running_position", 12)] if col_idx.get("running_position") and col_idx["running_position"] < len(cell_texts) else "",
                                "finish_time": cell_texts[col_idx.get("finish_time", 13)] if col_idx.get("finish_time") and col_idx["finish_time"] < len(cell_texts) else ""
                            }
                            results.append(result)
                    
                    race_data["results"] = results
                    
                    # ========== Extract PAYOUT ==========
                    # Use the new unified extraction method
                    race_data["payout"] = await self._extract_all_payouts(page)
                    
                    # ========== Extract INCIDENTS ==========
                    incidents = []
                    # Look for incident table - find it again since we removed payout_tables
                    all_tables = await page.query_selector_all("table")
                    for table in all_tables:
                        table_text = await table.inner_text()
                        if "事故報告" in table_text or "無敵" in table_text:
                            rows = await table.query_selector_all("tr")
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 3:
                                    cell_texts = [(await c.inner_text()).strip() for c in cells]
                                    if cell_texts[0].isdigit():
                                        incidents.append({
                                            "rank": int(cell_texts[0]),
                                            "horse_number": int(cell_texts[1]) if cell_texts[1].isdigit() else 0,
                                            "horse_name": cell_texts[2] if len(cell_texts) > 2 else "",
                                            "incident_report": cell_texts[3] if len(cell_texts) > 3 else ""
                                        })
                    
                    race_data["incidents"] = incidents
                    
                    # Save to merged collection
                    race_data = add_timestamps(race_data)
                    self.db.db["races"].replace_one({"hkjc_race_id": race_key}, race_data, upsert=True)
                    
                    print(f"   ✅ {race_key}: {len(results)} horses, payout={len(race_data['payout'])}, incidents={len(incidents)}")
                    self.stats["races"] += 1
                    
                    # Update race queue
                    try:
                        race_queue = get_race_queue()
                        race_queue.connect()
                        race_queue.update_status(race_key, {
                            "results": len(results),
                            "payout": len(race_data["payout"]),
                            "incidents": len(incidents)
                        })
                    except:
                        pass
                    
                    # Log successful race scrape
                    self.activity_log.log_complete(
                        phase="race_result",
                        race_id=race_key,
                        records_count=len(results)
                    )
                    
                except Exception as e:
                    print(f"   ❌ {race_key}: {e}")
                    self.stats["errors"].append({"race": race_key, "error": str(e)})
                    self.activity_log.log_error(phase="race_result", race_id=race_key, error=str(e))
                    
                    # Update race queue as failed
                    try:
                        race_queue = get_race_queue()
                        race_queue.connect()
                        race_queue.mark_failed(race_key, str(e))
                    except:
                        pass
                
                finally:
                    await page.close()
        
        # Scrape all races (with resume support)
        if self.resume:
            processed_races = self.activity_log.get_processed_races()
            races_to_scrape = {k: v for k, v in race_urls.items() if k not in processed_races}
            skipped = len(race_urls) - len(races_to_scrape)
            if skipped > 0:
                print(f"   ⏭️  Skipping {skipped} already processed races (resume mode)")
        else:
            races_to_scrape = race_urls
        
        tasks = [scrape_race(k, v) for k, v in races_to_scrape.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _extract_payout_simple(self, table, bet_type: str) -> List[Dict]:
        """Extract payout data from a table - handles HKJC's single table format"""
        payout_list = []
        try:
            rows = await table.query_selector_all("tr")
            
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 3:
                    # Column structure: 彩池 | 勝出組合 | 派彩
                    pool_name = (await cells[0].inner_text()).strip()
                    combination = (await cells[1].inner_text()).strip()
                    payout_str = (await cells[2].inner_text()).strip()
                    
                    # Parse payout
                    payout_str = payout_str.replace("$", "").replace(",", "").strip()
                    try:
                        payout = float(payout_str)
                    except:
                        payout = 0.0
                    
                    # Skip header rows
                    if pool_name in ["彩池", "勝出組合", "派彩 (HK$)", ""]:
                        continue
                    
                    # Skip if no valid combination or payout
                    if not combination or payout <= 0:
                        continue
                    
                    payout_list.append({
                        "combination": combination,
                        "payout": payout
                    })
                    
        except Exception as e:
            logger.error(f"Error extracting payout: {e}")
        return payout_list
    
    async def _extract_all_payouts(self, page) -> Dict:
        """Extract all payouts from the page - handles the single table format with merged cells"""
        payout = {}
        
        try:
            # Find the payout table (contains "派彩")
            tables = await page.query_selector_all("table")
            
            payout_table = None
            for table in tables:
                text = await table.inner_text()
                if "派彩" in text and "彩池" in text:
                    payout_table = table
                    break
            
            if not payout_table:
                return payout
            
            # Extract all rows
            rows = await payout_table.query_selector_all("tr")
            current_pool = None  # Track current pool for merged cells
            
            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    # Handle merged cells - due to rowspan, some rows have fewer cells
                    # If row has only 1 cell, skip (probably header or empty)
                    if len(cells) == 1:
                        continue
                    # If row has only 2 cells, it's a continuation of previous pool (rowspan)
                    elif len(cells) == 2:
                        # First cell is missing due to rowspan - use previous pool
                        if current_pool:
                            pool_name = current_pool
                            combination = (await cells[0].inner_text()).strip()
                            payout_str = (await cells[1].inner_text()).strip()
                        else:
                            continue  # No previous pool, skip
                    else:
                        # Normal row with 3 cells
                        pool_name = (await cells[0].inner_text()).strip() if len(cells) > 0 else ""
                        combination = (await cells[1].inner_text()).strip() if len(cells) > 1 else ""
                        payout_str = (await cells[2].inner_text()).strip() if len(cells) > 2 else ""
                    
                    # Skip header row
                    if pool_name in ["彩池", "勝出組合", "派彩 (HK$)"]:
                        continue
                    
                    # Update current pool for next row
                    if pool_name and pool_name not in ["彩池", "勝出組合", "派彩 (HK$)"]:
                        current_pool = pool_name
                    
                    # Parse payout
                    payout_str = payout_str.replace("$", "").replace(",", "").strip()
                    try:
                        payout_val = float(payout_str)
                    except:
                        payout_val = 0.0
                    
                    # Skip invalid
                    if not combination or payout_val <= 0:
                        continue
                    
                    # Map pool names to our schema
                    pool_key = None
                    if pool_name == "獨贏":
                        pool_key = "win"
                    elif pool_name == "位置":
                        pool_key = "place"
                    elif pool_name == "連贏":
                        pool_key = "quinella"
                    elif pool_name == "位置Q" or pool_name == "位置孖寶":
                        pool_key = "quinella_place"
                    elif pool_name == "二重彩":
                        pool_key = "forecast"
                    elif pool_name == "三重彩":
                        pool_key = "tierce"
                    elif pool_name == "單T":
                        pool_key = "trio"
                    elif pool_name == "四連環":
                        pool_key = "first_4"
                    elif pool_name == "四重彩":
                        pool_key = "quartet"
                    elif "孖寶" in pool_name or "口孖寶" in pool_name:
                        pool_key = "double"
                    elif "三寶" in pool_name or "口三寶" in pool_name:
                        pool_key = "treble"
                    elif "孖T" in pool_name and "三T" not in pool_name:
                        pool_key = "double_trio"
                    elif "三T" in pool_name and "安慰" not in pool_name:
                        pool_key = "triple_trio"
                    elif "三T(安慰獎)" in pool_name or "三T安慰" in pool_name:
                        pool_key = "triple_trio_consolation"
                    elif "六環彩" in pool_name:
                        pool_key = "six_up"
                    elif "騎師王" in pool_name:
                        pool_key = "jockey_challenge"
                    elif "練馬師王" in pool_name:
                        pool_key = "trainer_challenge"
                    
                    if pool_key:
                        if pool_key not in payout:
                            payout[pool_key] = []
                        payout[pool_key].append({
                            "combination": combination,
                            "payout": payout_val
                        })
            
            # Handle jockey_challenge and trainer_challenge specially (different format)
            # They have links to details, need to extract differently
            
        except Exception as e:
            logger.error(f"Error extracting all payouts: {e}")
        
        return payout
        payout_list = []
        try:
            rows = await table.query_selector_all("tr")
            
            # Find the header row to determine columns
            header_row = rows[0] if rows else None
            header_text = await header_row.inner_text() if header_row else ""
            
            # Find the column index for the bet type
            cells = await header_row.query_selector_all("th") if header_row else []
            header_cells = [await c.inner_text() for c in cells]
            
            header_tds = await header_row.query_selector_all("td") if header_row else []
            header_cells += [await c.inner_text() for c in header_tds]
            
            # Find column index for this bet type
            col_idx = -1
            for i, h in enumerate(header_cells):
                if bet_type in h:
                    col_idx = i
                    break
            
            # If we found the column, extract data
            if col_idx >= 0:
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) > col_idx:
                        combo = (await cells[0].inner_text()).strip()
                        div_cell = (await cells[col_idx].inner_text()).strip() if col_idx < len(cells) else ""
                        
                        # Parse dividend (remove $ and ,)
                        div_cell = div_cell.replace("$", "").replace(",", "")
                        try:
                            dividend = float(div_cell)
                        except:
                            dividend = 0.0
                        
                        if combo and dividend > 0:
                            payout_list.append({
                                "combination": combo,
                                "payout": dividend
                            })
            else:
                # Fallback: if no column found, extract all
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 2:
                        combo = (await cells[0].inner_text()).strip()
                        div_str = (await cells[1].inner_text()).strip()
                        
                        div_str = div_str.replace("$", "").replace(",", "")
                        try:
                            dividend = float(div_str)
                        except:
                            dividend = 0.0
                        
                        if combo and dividend > 0:
                            payout_list.append({
                                "combination": combo,
                                "payout": dividend
                            })
        except Exception as e:
            logger.error(f"Error extracting payout for {bet_type}: {e}")
        return payout_list
    
    async def _extract_payout_with_prefix(self, table, bet_type: str) -> List[Dict]:
        """Extract payout with 第X口 prefix (孖寶, 三寶, 孖T)"""
        payout_list = []
        try:
            rows = await table.query_selector_all("tr")
            
            for row in rows[1:]:  # Skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    combo = (await cells[0].inner_text()).strip()
                    div_str = (await cells[1].inner_text()).strip()
                    
                    # Parse dividend
                    div_str = div_str.replace("$", "").replace(",", "")
                    try:
                        dividend = float(div_str)
                    except:
                        dividend = 0.0
                    
                    if combo and dividend > 0:
                        # Add 第X口 prefix if present
                        payout_list.append({
                            "combination": combo,
                            "payout": dividend
                        })
        except Exception as e:
            logger.error(f"Error extracting payout with prefix for {bet_type}: {e}")
        return payout_list
    
    async def _extract_payout_six_up(self, table) -> List[Dict]:
        """Extract Six Up (六環彩) payouts"""
        payout_list = []
        try:
            rows = await table.query_selector_all("tr")
            
            for row in rows[1:]:  # Skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    combo = (await cells[0].inner_text()).strip()
                    div_str = (await cells[1].inner_text()).strip()
                    
                    div_str = div_str.replace("$", "").replace(",", "")
                    try:
                        dividend = float(div_str)
                    except:
                        dividend = 0.0
                    
                    if combo and dividend > 0:
                        payout_list.append({
                            "combination": combo,
                            "payout": dividend
                        })
        except Exception as e:
            logger.error(f"Error extracting six_up payout: {e}")
        return payout_list
    
    async def _extract_payout_jockey_trainer(self, table, bet_type: str) -> List[Dict]:
        """Extract Jockey/Trainer Challenge (騎師王/練馬師王)"""
        payout_list = []
        try:
            rows = await table.query_selector_all("tr")
            
            for row in rows[1:]:  # Skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 2:
                    combo = (await cells[0].inner_text()).strip()
                    name = (await cells[1].inner_text()).strip()
                    
                    if combo:
                        entry = {"combination": combo}
                        if name:
                            if bet_type == "騎師王":
                                entry["jockey_name"] = name
                            else:
                                entry["trainer_name"] = name
                        payout_list.append(entry)
        except Exception as e:
            logger.error(f"Error extracting {bet_type} payout: {e}")
        return payout_list
    
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
    """Entry point with command-line options"""
    import argparse
    
    parser = argparse.ArgumentParser(description="HKJC Complete Scraper")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh (ignore previous progress)")
    parser.add_argument("--clear-log", action="store_true", help="Clear activity log before starting")
    parser.add_argument("--show-log", action="store_true", help="Show activity log and exit")
    parser.add_argument("-c", "--concurrent", type=int, default=2, help="Max concurrent scrapes (default: 2)")
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode (visible)")
    parser.add_argument("--phase3-only", action="store_true", help="Only run Phase 1-3, skip Phase 4")
    parser.add_argument("--phase4-only", action="store_true", help="Only run Phase 4, skip Phase 1-3")
    
    args = parser.parse_args()
    
    # Handle activity log options
    activity_log = get_activity_log()
    
    if args.show_log:
        activity_log.print_summary()
        return
    
    if args.clear_log:
        activity_log.clear()
        print("🗑️  Activity log cleared")
    
    # Run scraper
    resume = not args.no_resume
    headless = not args.headful
    
    scraper = HKJCCompleteScraper(
        max_concurrent=args.concurrent, 
        headless=headless,
        resume=resume
    )
    scraper.phase3_only = args.phase3_only
    scraper.phase4_only = args.phase4_only
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
