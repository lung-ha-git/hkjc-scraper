"""
HKJC Race Card Scraper
Scrape race card information (排位表) - per race basis

URL: https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=YYYY/MM/DD&Racecourse=HV&RaceNo=X
"""

import asyncio
import re
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page
from typing import Dict, List, Optional
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class RaceCardScraper:
    """Scrape HKJC race cards - per race"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/racecard"
    
    def __init__(self, headless: bool = True, delay: int = 2):
        self.headless = headless
        self.delay = delay
        self.browser = None
        self.playwright = None
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    def _build_url(self, race_date: str, venue: str = "HV", race_no: int = 1) -> str:
        """Build URL for specific race"""
        # Convert YYYY-MM-DD to YYYY/MM/DD
        date_parts = race_date.split("-")
        ddmmyyyy = f"{date_parts[0]}/{date_parts[1]}/{date_parts[2]}"
        return f"{self.BASE_URL}?racedate={ddmmyyyy}&Racecourse={venue}&RaceNo={race_no}"
    
    async def scrape_race(self, race_date: str, venue: str = "HV", race_no: int = 1) -> Optional[Dict]:
        """
        Scrape a single race card
        
        Args:
            race_date: Format YYYY-MM-DD (e.g., "2026-03-18")
            venue: HV (跑馬地) or ST (沙田)
            race_no: Race number (1-12)
        
        Returns:
            Race card data or None if not found
        """
        url = self._build_url(race_date, venue, race_no)
        logger.info(f"🏇 Scraping race {race_no} ({venue})...")
        
        # Create context
        context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)
            
            # Check if race exists
            text = await page.inner_text("body")
            
            if "沒有相關資料" in text or "找不到" in text or len(text) < 500:
                logger.info(f"   No data for race {race_no}")
                await context.close()
                return None
            
            # Extract race info
            race_info = await self._extract_race(page, race_date, venue, race_no)
            
            await context.close()
            return race_info
            
        except Exception as e:
            logger.error(f"Error scraping race {race_no}: {e}")
            await context.close()
            return None
    
    async def scrape_race_day(self, race_date: str, venue: str = "HV", max_races: int = 12) -> List[Dict]:
        """
        Scrape all races for a given day
        
        Args:
            race_date: Format YYYY-MM-DD
            venue: HV or ST
            max_races: Maximum races to try (default 12)
        
        Returns:
            List of race card data
        """
        logger.info(f"🏇 Scraping race day {race_date} ({venue})...")
        
        racecards = []
        
        for race_no in range(1, max_races + 1):
            race_info = await self.scrape_race(race_date, venue, race_no)
            
            if race_info is None:
                # No more races
                logger.info(f"   No more races after race {race_no - 1}")
                break
            
            racecards.append(race_info)
            logger.info(f"   ✅ Race {race_no}: {len(race_info.get('horses', []))} horses")
        
        logger.info(f"   ✅ Found {len(racecards)} races")
        return racecards
    
    async def _extract_race(self, page: Page, race_date: str, venue: str, race_no: int) -> Dict:
        """Extract race metadata and horses from page"""
        
        text = await page.inner_text("body")
        
        race_meta = {
            "race_no": race_no,
            "race_date": race_date,
            "venue": venue,
        }
        
        # Extract race name
        name_match = re.search(r'第\s*' + str(race_no) + r'\s*場\s*[-–—]\s*([^\n]+?)(?:\n|$)', text)
        if name_match:
            race_meta["race_name"] = name_match.group(1).strip()
        
        # Extract race time
        time_match = re.search(r'(\d{1,2}:\d{2})', text)
        if time_match:
            race_meta["race_time"] = time_match.group(1)
        
        # Extract course and distance
        dist_match = re.search(r'(草地|全天候跑道|泥地).*?(\d+)米', text)
        if dist_match:
            course_map = {"草地": "TURF", "全天候跑道": "AWT", "泥地": "DIRT"}
            race_meta["course"] = course_map.get(dist_match.group(1), dist_match.group(1))
            race_meta["distance"] = int(dist_match.group(2))
        
        # Extract track condition
        track_match = re.search(r'(好地|快地|軟地|黏地|爛地)', text)
        if track_match:
            race_meta["track_condition"] = track_match.group(1)
        
        # Extract prize
        prize_match = re.search(r'獎金[:：]\s*\$?([\d,]+)', text)
        if prize_match:
            race_meta["prize"] = int(prize_match.group(1).replace(",", ""))
        
        # Extract rating class
        rating_match = re.search(r'評分[:：]\s*(\d+)-(\d+)', text)
        if rating_match:
            race_meta["rating_range"] = f"{rating_match.group(1)}-{rating_match.group(2)}"
        
        # Extract class
        class_match = re.search(r'(一級賽|二級賽|三級賽|一班|二班|三班|四班|五班|新馬)', text)
        if class_match:
            race_meta["class"] = class_match.group(1)
        
        # Extract horses
        horses = await self._extract_horses(page)
        race_meta["horses"] = horses
        
        return race_meta
    
    async def _extract_horses(self, page: Page) -> List[Dict]:
        """Extract horse entries from table"""
        horses = []
        
        try:
            tables = await page.query_selector_all("table")
            
            # Find horse table
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 5:
                    continue
                
                # Check if horse table
                first_row = await rows[1].query_selector_all("td") if len(rows) > 1 else []
                if not first_row:
                    continue
                    
                first_cell = (await first_row[0].inner_text()).strip() if first_row else ""
                
                if first_cell.isdigit():
                    # Found horse table
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) < 10:
                            continue
                        
                        horse = await self._extract_horse_entry(cells)
                        if horse:
                            horse_no = int((await cells[0].inner_text()).strip())
                            horse["horse_no"] = horse_no
                            horses.append(horse)
                    break
            
        except Exception as e:
            logger.warning(f"Error extracting horses: {e}")
        
        return horses
    
    async def _extract_horse_entry(self, cells) -> Optional[Dict]:
        """Extract data from a horse row"""
        try:
            if len(cells) < 10:
                return None
            
            # Cell mapping based on actual page structure:
            # 0: horse_no, 1: recent_form, 2: empty, 3: horse_name, 4: horse_code,
            # 5: weight_carried, 6: jockey_name, 7: empty, 8: draw, 9: trainer_name, ...
            
            # Horse name (cell 3)
            horse_name = (await cells[3].inner_text()).strip()
            
            # Horse ID from cell 4 (code like K290)
            horse_id = (await cells[4].inner_text()).strip()
            
            # Weight carried (cell 5)
            weight_text = (await cells[5].inner_text()).strip()
            try:
                weight_carried = int(weight_text)
            except ValueError:
                weight_carried = None
            
            # Jockey name (cell 6)
            jockey_name = (await cells[6].inner_text()).strip()
            
            # Draw (檔位) (cell 8)
            draw_text = (await cells[8].inner_text()).strip()
            try:
                draw = int(draw_text) if draw_text.isdigit() else None
            except ValueError:
                draw = None
            
            # Trainer name (cell 9)
            trainer_name = (await cells[9].inner_text()).strip()
            
            # Rating (cell 10) - check if it's a number
            rating_text = (await cells[10].inner_text()).strip()
            try:
                rating = int(rating_text) if rating_text.isdigit() else None
            except ValueError:
                rating = None
            
            # Rating change (cell 11)
            rating_change_text = (await cells[11].inner_text()).strip()
            try:
                rating_change = int(rating_change_text) if rating_change_text.replace("-", "").isdigit() else 0
            except ValueError:
                rating_change = 0
            
            # Scratch weight (排位體重) (cell 12)
            weight_text = (await cells[12].inner_text()).strip()
            try:
                scratch_weight = int(weight_text) if weight_text.isdigit() else None
            except ValueError:
                scratch_weight = None
            
            # Recent form (近績) (cell 1)
            recent_form = (await cells[1].inner_text()).strip() if len(cells) > 1 else ""
            
            # Equipment (配備) - cell 17
            equipment = (await cells[17].inner_text()).strip() if len(cells) > 17 else ""
            
            return {
                "horse_id": horse_id,
                "horse_name": horse_name,
                "weight_carried": weight_carried,
                "jockey_name": jockey_name,
                "draw": draw,
                "trainer_name": trainer_name,
                "rating": rating,
                "rating_change": rating_change,
                "scratch_weight": scratch_weight,
                "recent_form": recent_form,
                "equipment": equipment
            }
            
        except Exception as e:
            logger.warning(f"Error extracting horse entry: {e}")
            return None
    
    def save_to_mongodb(self, racecards: List[Dict]) -> bool:
        """Save race cards to MongoDB"""
        logger.info("💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            logger.error("Cannot connect to MongoDB")
            return False
        
        total_horses = 0
        
        for card in racecards:
            race_date = card.get("race_date")
            race_no = card.get("race_no")
            venue = card.get("venue", "ST")
            
            race_id = f"{race_date.replace('-', '_')}_{venue}_{race_no}"
            
            # Save race card metadata
            race_doc = {
                "race_id": race_id,
                "race_date": race_date,
                "venue": venue,
                "race_no": race_no,
                "race_name": card.get("race_name"),
                "race_time": card.get("race_time"),
                "course": card.get("course"),
                "distance": card.get("distance"),
                "track_condition": card.get("track_condition"),
                "prize": card.get("prize"),
                "rating_range": card.get("rating_range"),
                "class": card.get("class"),
                "scraped_at": datetime.now().isoformat(),
                "source": "racecard"
            }
            
            db.db["racecards"].update_one(
                {"race_id": race_id},
                {"$set": race_doc},
                upsert=True
            )
            
            # Save horse entries
            horses = card.get("horses", [])
            total_horses += len(horses)
            
            for horse in horses:
                horse["race_id"] = race_id
                horse["race_date"] = race_date
                horse["venue"] = venue
                horse["race_no"] = race_no
            
            if horses:
                # Delete old entries and insert new
                db.db["racecard_entries"].delete_many({"race_id": race_id})
                db.db["racecard_entries"].insert_many(horses)
            
            logger.info(f"   ✅ Race {race_no}: {len(horses)} horses")
        
        db.disconnect()
        logger.info(f"   ✅ Total: {total_horses} horses across {len(racecards)} races")
        
        return True


async def main():
    """Test the scraper"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape HKJC Race Cards")
    parser.add_argument("--date", type=str, default="2026-03-18", help="Race date (YYYY-MM-DD)")
    parser.add_argument("--venue", type=str, default="HV", help="Venue: HV or ST")
    parser.add_argument("--race-no", type=int, help="Specific race number")
    parser.add_argument("--save", action="store_true", help="Save to MongoDB")
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    async with RaceCardScraper(headless=True, delay=2) as scraper:
        if args.race_no:
            # Scrape single race
            racecard = await scraper.scrape_race(args.date, args.venue, args.race_no)
            if racecard:
                print(f"\n🏇 Race {racecard['race_no']}: {racecard.get('race_name', 'N/A')}")
                print(f"   Venue: {racecard.get('venue')}, Distance: {racecard.get('distance')}m")
                print(f"   Horses: {len(racecard.get('horses', []))}")
                for horse in racecard.get('horses', [])[:5]:
                    print(f"      {horse['horse_no']}. {horse['horse_name']} ({horse['jockey_name']})")
            else:
                print("❌ No race data found")
        else:
            # Scrape full race day
            racecards = await scraper.scrape_race_day(args.date, args.venue)
            
            print(f"\n📊 Found {len(racecards)} races")
            
            for card in racecards:
                print(f"\n🏇 Race {card['race_no']}: {card.get('race_name', 'N/A')}")
                print(f"   Venue: {card.get('venue')}, Distance: {card.get('distance')}m")
                print(f"   Horses: {len(card.get('horses', []))}")
            
            if args.save and racecards:
                scraper.save_to_mongodb(racecards)


if __name__ == "__main__":
    asyncio.run(main())
