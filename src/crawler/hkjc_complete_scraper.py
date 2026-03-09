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
                    title = await page.title()
                    
                    # Extract comprehensive horse info
                    horse_data = {"hkjc_horse_id": horse_id}
                    
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
                    self.db.db["horses"].replace_one(
                        {"hkjc_horse_id": horse_id}, 
                        horse_data, 
                        upsert=True
                    )
                    
                    self.stats["horses"] += 1
                    
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
                    
                    # Task 1: 馬匹評分/體重/名次
                    try:
                        await page.click("text=馬匹評分/體重/名次", timeout=3000)
                        await asyncio.sleep(2)
                        
                        # Parse the rating table
                        tables = await page.query_selector_all("table.bigborder")
                        
                        rating_by_date = {}
                        
                        for table in tables:
                            rows = await table.query_selector_all("tr")
                            
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) < 10:
                                    continue
                                
                                # Extract date as key
                                date = (await cells[2].inner_text()).strip()
                                if not date:
                                    continue
                                
                                # Get position/total
                                position = (await cells[1].inner_text()).strip()
                                result = f"{position}"
                                
                                rating_by_date[date] = {
                                    "rating": (await cells[8].inner_text()).strip() if len(cells) > 8 else "",
                                    "result": result,
                                    "weight": (await cells[16].inner_text()).strip() if len(cells) > 16 else "",
                                    "track": (await cells[3].inner_text()).strip() if len(cells) > 3 else "",
                                    "surface": "草地" if "草" in (await cells[3].inner_text()) else "全天候",
                                    "distance": (await cells[4].inner_text()).strip() if len(cells) > 4 else "",
                                    "course": (await cells[5].inner_text()).strip() if len(cells) > 5 else "",
                                    "condition": (await cells[6].inner_text()).strip() if len(cells) > 6 else "",
                                    "class": (await cells[7].inner_text()).strip() if len(cells) > 7 else "",
                                }
                        
                        # Save to horses collection
                        if rating_by_date:
                            self.db.db["horses"].update_one(
                                {"hkjc_horse_id": horse_id},
                                {"$set": {"ratings_by_date": rating_by_date}}
                            )
                    except Exception as e:
                        pass
                    
                    # Task 2: 所跑途程賽績紀錄 - Use dedicated URL with proper parsing
                    try:
                        perf_url = f"https://racing.hkjc.com/zh-hk/local/information/performance?horseid={horse_id}"
                        await page.goto(perf_url, wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        # Initialize structure
                        dist_perf = {
                            "hkjc_horse_id": horse_id,
                            "track_performance": [],
                            "distance_performance": {},
                            "seasonal_performance": [],
                            "overall_total": {}
                        }
                        
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
                                    continue
                                elif cell_texts[0] == '歷季成績':
                                    current_section = 'season'
                                    continue
                                
                                # Skip summary rows
                                if any(x in cell_texts[1] for x in ['總成績', '總']):
                                    continue
                                
                                # Parse track performance
                                if current_section == 'track':
                                    surface = cell_texts[0] if cell_texts[0] else surface
                                    condition = cell_texts[1]
                                    
                                    if len(cell_texts) >= 5 and condition not in ['總成績']:
                                        dist_perf["track_performance"].append({
                                            "surface": surface if '草地' in str(surface) or '全天候' in str(surface) else '草地',
                                            "condition": condition,
                                            "starts": cell_texts[2],
                                            "win": cell_texts[3],
                                            "2nd": cell_texts[4],
                                            "3rd": cell_texts[5],
                                            "unplaced": cell_texts[6] if len(cell_texts) > 6 else '0'
                                        })
                                
                                # Parse distance performance
                                elif current_section == 'distance':
                                    if cell_texts[0]:
                                        current_dist = cell_texts[0]
                                    if len(cell_texts) >= 5:
                                        dist_perf["distance_performance"].setdefault(current_dist, []).append({
                                            "distance": cell_texts[1],
                                            "starts": cell_texts[2],
                                            "win": cell_texts[3],
                                            "2nd": cell_texts[4],
                                            "3rd": cell_texts[5],
                                            "unplaced": cell_texts[6] if len(cell_texts) > 6 else '0'
                                        })
                                
                                # Parse seasonal performance
                                elif current_section == 'season':
                                    if len(cell_texts) >= 5 and cell_texts[1] not in ['總成績']:
                                        dist_perf["seasonal_performance"].append({
                                            "season": cell_texts[1],
                                            "starts": cell_texts[2],
                                            "win": cell_texts[3],
                                            "2nd": cell_texts[4],
                                            "3rd": cell_texts[5],
                                            "unplaced": cell_texts[6] if len(cell_texts) > 6 else '0'
                                        })
                        
                        # Save
                        existing = self.db.db["horse_distance_stats"].find_one({
                            "hkjc_horse_id": horse_id
                        })
                        if not existing and (dist_perf["track_performance"] or dist_perf["distance_performance"]):
                            self.db.db["horse_distance_stats"].insert_one(dist_perf)
                    except:
                        pass
                        pass
                    
                    # Task 3: 晨操紀錄
                    try:
                        await page.click("text=晨操紀錄", timeout=3000)
                        await asyncio.sleep(2)
                        
                        tables = await page.query_selector_all("table.table_bd")
                        
                        for table in tables:
                            rows = await table.query_selector_all("tr")
                            
                            for row in rows[1:]:
                                cells = await row.query_selector_all("td")
                                if len(cells) >= 2:
                                    workout = {
                                        "hkjc_horse_id": horse_id,
                                        "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                        "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                    }
                                    
                                    if workout.get("date"):
                                        self.db.db["horse_workouts"].insert_one(workout)
                    except:
                        pass
                    
                    # Task 4: 傷患紀錄
                    try:
                        await page.click("text=傷患紀錄", timeout=3000)
                        await asyncio.sleep(2)
                        
                        # Find table
                        tables = await page.query_selector_all("table.table_bd")
                        
                        medical_count = 0
                        for table in tables:
                            rows = await table.query_selector_all("tr")
                            if len(rows) > 1:
                                # Check header
                                header = await rows[0].inner_text()
                                if "傷患" in header or "日期" in header:
                                    medical_count = len(rows) - 1
                                    
                                    for row in rows[1:]:
                                        cells = await row.query_selector_all("td")
                                        if len(cells) >= 2:
                                            med = {
                                                "hkjc_horse_id": horse_id,
                                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                            }
                                            self.db.db["horse_medical"].insert_one(med)
                                    break
                        
                    except Exception as e:
                        pass  # Silent fail
                    
                    # Task 5: 搬遷紀錄
                    try:
                        await page.click("text=搬遷紀錄", timeout=3000)
                        await asyncio.sleep(2)
                        
                        # Find movement table by id or by header
                        tables = await page.query_selector_all("table")
                        
                        for table in tables:
                            table_id = await table.get_attribute("id") or ""
                            
                            # Check if this is movement table
                            rows = await table.query_selector_all("tr")
                            if len(rows) > 1:
                                header = await rows[0].inner_text()
                                
                                if "MovementRecord" in table_id or "搬遷" in header:
                                    for row in rows[1:]:
                                        cells = await row.query_selector_all("td")
                                        if len(cells) >= 2:
                                            move = {
                                                "hkjc_horse_id": horse_id,
                                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                                            }
                                            
                                            if move.get("date"):
                                                self.db.db["horse_movements"].insert_one(move)
                                    break
                    except:
                        pass
                    
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
                                        self.db.db["horse_pedigree"].insert_one(pedigree)
                    except:
                        pass
                    
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
