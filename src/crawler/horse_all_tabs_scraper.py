"""
Complete Horse All Tabs Scraper
Scrapes all tabs: 往績、途程、晨操、傷患、搬遷、海外、彩衣
"""

import asyncio
import re
from playwright.async_api import async_playwright, Page
from datetime import datetime
from typing import Dict, List, Optional
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class HorseAllTabsScraper:
    """
    Complete scraper for all horse detail tabs
    Scrapes: race_history, distance_stats, workouts, medical, movements, overseas, jersey
    """
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    # Tab mapping (text on tab -> internal key)
    TAB_MAPPING = {
        "往績紀錄": "race_history",
        "所跑途程賽績紀錄": "distance_stats",
        "晨操紀錄": "workouts",
        "傷患紀錄": "medical",
        "搬遷紀錄": "movements",
        "海外賽績紀錄": "overseas",
        "血統簡評": "pedigree",
    }
    
    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
        self.hkjc_horse_id = None
        self.page = None
        self.context = None
        self.browser = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def scrape_horse(self, hkjc_horse_id: str) -> Dict:
        """
        Scrape all tabs for a horse
        
        Args:
            hkjc_horse_id: e.g., "HK_2023_J256"
            
        Returns:
            Dict with all scraped data
        """
        self.hkjc_horse_id = hkjc_horse_id
        url = f"{self.BASE_URL}?horseid={hkjc_horse_id}"
        
        print(f"\n🐴 Starting complete scrape for: {hkjc_horse_id}")
        print("=" * 80)
        
        self.page = await self.context.new_page()
        
        try:
            # Load initial page (shows race history by default)
            print(f"\n📱 Loading: {url}")
            await self.page.goto(url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            result = {
                "hkjc_horse_id": hkjc_horse_id,
                "url": url,
                "scraped_at": datetime.now().isoformat(),
            }
            
            # Scrape race history (default tab)
            print("\n📊 1. Scraping 往績紀錄 (default tab)...")
            result["race_history"] = await self._scrape_race_history()
            print(f"   ✅ {len(result['race_history'])} races scraped")
            
            # Find and click other tabs
            for tab_text, key in self.TAB_MAPPING.items():
                if key == "race_history":
                    continue  # Already done
                
                print(f"\n📊 {key.upper()}. Scraping {tab_text}...")
                
                try:
                    clicked = await self._click_tab(tab_text)
                    if clicked:
                        await self.page.wait_for_timeout(self.delay * 1000)
                        
                        if key == "distance_stats":
                            result[key] = await self._scrape_distance_stats()
                            track_count = len(result[key].get("venue_performance", []))
                            dist_count = len(result[key].get("distance_performance", []))
                            season_count = len(result[key].get("season_performance", []))
                            print(f"   ✅ venue: {track_count}, distance: {dist_count}, seasons: {season_count}")
                        elif key == "workouts":
                            result[key] = await self._scrape_workouts()
                            print(f"   ✅ {len(result[key])} scraped")
                        elif key == "medical":
                            result[key] = await self._scrape_medical()
                            print(f"   ✅ {len(result[key])} scraped")
                        elif key == "movements":
                            result[key] = await self._scrape_movements()
                            print(f"   ✅ {len(result[key])} scraped")
                        elif key == "overseas":
                            result[key] = await self._scrape_overseas()
                            print(f"   ✅ {len(result[key])} scraped")
                        elif key == "pedigree":
                            result[key] = await self._scrape_pedigree()
                            print(f"   ✅ data scraped")
                    else:
                        print(f"   ⚠️  Tab not found: {tab_text}")
                        result[key] = [] if key != "distance_stats" and key != "pedigree" else {}
                
                except Exception as e:
                    logger.error(f"Error scraping {tab_text}: {e}")
                    result[key] = {"error": str(e)} if key in ["distance_stats", "pedigree"] else []
            
            await self.page.close()
            return result
            
        except Exception as e:
            logger.error(f"Error in scrape_horse: {e}")
            await self.page.close()
            raise
    
    async def _click_tab(self, tab_text: str) -> bool:
        """Click on a tab by text"""
        try:
            selectors = [
                f"text='{tab_text}'",
                f"a:has-text('{tab_text}')",
                f"[role='tab']:has-text('{tab_text}')",
            ]
            
            for selector in selectors:
                try:
                    if await self.page.is_visible(selector, timeout=2000):
                        element = await self.page.query_selector(selector)
                        classes = await element.get_attribute("class")
                        if classes and "active" in classes:
                            return True
                        await self.page.click(selector)
                        return True
                except:
                    continue
            
            all_clickable = await self.page.query_selector_all("a, button, [role='tab'], li")
            for elem in all_clickable:
                text = await elem.inner_text()
                if tab_text in text:
                    await elem.click()
                    return True
            
            return False
        except Exception as e:
            logger.warning(f"Could not click tab {tab_text}: {e}")
            return False
    
    async def _scrape_race_history(self) -> List[Dict]:
        """Scrape race history table"""
        races = []
        try:
            tables = await self.page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 5:
                    continue
                header_cells = await rows[0].query_selector_all("th, td")
                header_text = await header_cells[0].inner_text() if len(header_cells) > 0 else ""
                if "場次" in header_text:
                    headers = [await c.inner_text() for c in header_cells]
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 10:
                            race_data = {"hkjc_horse_id": self.hkjc_horse_id}
                            for j, cell in enumerate(cells):
                                val = await cell.inner_text()
                                if j < len(headers):
                                    header = headers[j].strip().replace('\n', '_').replace('/', '_')
                                    race_data[header] = val.strip() if val else ""
                            races.append(race_data)
                    break
        except Exception as e:
            logger.error(f"Error in _scrape_race_history: {e}")
        return races
    
    async def _scrape_distance_stats(self) -> Dict:
        """Scrape distance analysis stats - NEW FORMAT WITH ENGLISH KEYS"""
        result = {
            "hkjc_horse_id": self.hkjc_horse_id,
            "venue_performance": [],
            "distance_performance": [],
            "season_performance": [],
            "scraped_at": datetime.now().isoformat()
        }
        
        try:
            # Use direct performance URL
            perf_url = f"https://racing.hkjc.com/zh-hk/local/information/performance?horseid={self.hkjc_horse_id}"
            await self.page.goto(perf_url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            tables = await self.page.query_selector_all("table")
            
            current_section = None
            current_surface = None  # For track performance: Turf or All Weather Track
            current_venue_en = None  # English venue name
            
            # Track totals for calculations
            track_totals = {"starts": 0, "win": 0, "second": 0, "third": 0, "unplaced": 0}
            season_totals = {"starts": 0, "win": 0, "second": 0, "third": 0, "unplaced": 0}
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                
                for row in rows:
                    cells = await row.query_selector_all("td, th")
                    if not cells:
                        continue
                    
                    cell_texts = [(await c.inner_text()).strip() for c in cells]
                    first_text = cell_texts[0] if cell_texts[0] else ""
                    second_text = cell_texts[1] if len(cell_texts) > 1 else ""
                    
                    # Check section headers
                    if "場地成績" in first_text or first_text == "場地成績":
                        current_section = "track"
                        continue
                    elif "路程成績" in first_text or first_text == "路程成績":
                        current_section = "distance"
                        current_venue_en = None
                        continue
                    elif "歷季成績" in first_text or first_text == "歷季成績":
                        current_section = "season"
                        continue
                    
                    # Skip empty rows
                    if not first_text and not second_text:
                        continue
                    
                    # Track performance section
                    if current_section == "track":
                        # Check if this is a new surface row or continuation
                        if first_text and "總" not in first_text:
                            # New surface row - update current surface
                            current_surface = "Turf" if "草" in first_text else "All Weather Track"
                        
                        if not current_surface:
                            continue
                        if "總" in first_text or "總" in second_text:
                            continue
                        
                        condition = second_text
                        if not condition or "總" in condition:
                            continue
                        
                        # Map condition to English
                        condition_map = {
                            "好地至快地": "Good to Firm",
                            "好地": "Good",
                            "好地至黏地": "Good to Soft",
                            "黏地": "Soft",
                            "軟地": "Yielding",
                            "大爛地": "Heavy"
                        }
                        condition_en = condition_map.get(condition, condition)
                        
                        surface_type = current_surface
                        
                        starts = cell_texts[2].strip() if len(cell_texts) > 2 else "0"
                        win = cell_texts[3].strip() if len(cell_texts) > 3 else "0"
                        second = cell_texts[4].strip() if len(cell_texts) > 4 else "0"
                        third = cell_texts[5].strip() if len(cell_texts) > 5 else "0"
                        unplaced = cell_texts[6].strip() if len(cell_texts) > 6 else "0"
                        
                        if not starts.isdigit():
                            continue
                        
                        starts_int = int(starts)
                        win_int = int(win)
                        second_int = int(second)
                        third_int = int(third)
                        unplaced_int = int(unplaced)
                        
                        result["venue_performance"].append({
                            "track": surface_type,
                            "condition": condition_en,
                            "starts": starts_int,
                            "win": win_int,
                            "second": second_int,
                            "third": third_int,
                            "unplaced": unplaced_int
                        })
                        
                        # Accumulate totals
                        track_totals["starts"] += starts_int
                        track_totals["win"] += win_int
                        track_totals["second"] += second_int
                        track_totals["third"] += third_int
                        track_totals["unplaced"] += unplaced_int
                    
                    # Distance performance section
                    elif current_section == "distance":
                        # Check if this is a venue header row (e.g., "沙田草地", "跑馬地草地")
                        is_venue_header = False
                        if first_text and ("沙田" in first_text or "跑馬地" in first_text):
                            # Check if second column contains a distance (ends with 米)
                            # If yes, this is a data row, not just a header
                            if second_text and "米" in second_text:
                                # This is a data row with venue in first column
                                if "沙田" in first_text:
                                    if "草地" in first_text:
                                        current_venue_en = "Sha Tin Turf"
                                    elif "全天候" in first_text:
                                        current_venue_en = "Sha Tin All Weather"
                                elif "跑馬地" in first_text:
                                    current_venue_en = "Happy Valley Turf"
                            else:
                                # This is a header row (no distance in second column)
                                is_venue_header = True
                                if "沙田" in first_text:
                                    if "草地" in first_text:
                                        current_venue_en = "Sha Tin Turf"
                                    elif "全天候" in first_text:
                                        current_venue_en = "Sha Tin All Weather"
                                elif "跑馬地" in first_text:
                                    current_venue_en = "Happy Valley Turf"
                                continue
                        
                        if not current_venue_en:
                            continue
                        
                        # Total row for this venue
                        if "總" in first_text or "總" in second_text:
                            # For total row, find where the numbers start
                            data_start = 2 if (not first_text or "總" in first_text) else 1
                            
                            total_starts = int(cell_texts[data_start]) if len(cell_texts) > data_start and cell_texts[data_start].isdigit() else 0
                            total_win = int(cell_texts[data_start + 1]) if len(cell_texts) > data_start + 1 and cell_texts[data_start + 1].isdigit() else 0
                            total_second = int(cell_texts[data_start + 2]) if len(cell_texts) > data_start + 2 and cell_texts[data_start + 2].isdigit() else 0
                            total_third = int(cell_texts[data_start + 3]) if len(cell_texts) > data_start + 3 and cell_texts[data_start + 3].isdigit() else 0
                            total_unplaced = int(cell_texts[data_start + 4]) if len(cell_texts) > data_start + 4 and cell_texts[data_start + 4].isdigit() else 0
                            
                            result["distance_performance"].append({
                                "venue": f"{current_venue_en} Total",
                                "distance": "All",
                                "starts": total_starts,
                                "win": total_win,
                                "second": total_second,
                                "third": total_third,
                                "unplaced": total_unplaced
                            })
                            continue
                        
                        # Distance row (e.g., "1200米", "1400米", or venue + distance)
                        if first_text and "米" in first_text:
                            # First column is the distance
                            distance = first_text.strip()
                            data_start = 1
                        elif second_text and "米" in second_text:
                            # Second column is the distance
                            distance = second_text.strip()
                            data_start = 2
                        else:
                            # Neither column has distance, skip
                            continue
                        
                        if not distance or "總" in distance:
                            continue
                        
                        # Convert distance format: "1200米" -> "1200m"
                        if distance.endswith("米"):
                            distance = distance[:-1] + "m"
                        
                        starts = cell_texts[data_start].strip() if len(cell_texts) > data_start else "0"
                        if not starts.isdigit():
                            continue
                        
                        result["distance_performance"].append({
                            "venue": current_venue_en,
                            "distance": distance,
                            "starts": int(starts),
                            "win": int(cell_texts[data_start + 1]) if len(cell_texts) > data_start + 1 and cell_texts[data_start + 1].isdigit() else 0,
                            "second": int(cell_texts[data_start + 2]) if len(cell_texts) > data_start + 2 and cell_texts[data_start + 2].isdigit() else 0,
                            "third": int(cell_texts[data_start + 3]) if len(cell_texts) > data_start + 3 and cell_texts[data_start + 3].isdigit() else 0,
                            "unplaced": int(cell_texts[data_start + 4]) if len(cell_texts) > data_start + 4 and cell_texts[data_start + 4].isdigit() else 0
                        })
                    
                    # Seasonal performance section
                    elif current_section == "season":
                        season = first_text.strip() if first_text else second_text.strip()
                        if not season:
                            continue
                        
                        # Skip if it's a total row here, we'll add it at the end
                        if "總" in season:
                            continue
                        
                        data_start = 1 if first_text else 2
                        starts = cell_texts[data_start].strip() if len(cell_texts) > data_start else "0"
                        if not starts.isdigit():
                            continue
                        
                        starts_int = int(starts)
                        win_int = int(cell_texts[data_start + 1]) if len(cell_texts) > data_start + 1 and cell_texts[data_start + 1].isdigit() else 0
                        second_int = int(cell_texts[data_start + 2]) if len(cell_texts) > data_start + 2 and cell_texts[data_start + 2].isdigit() else 0
                        third_int = int(cell_texts[data_start + 3]) if len(cell_texts) > data_start + 3 and cell_texts[data_start + 3].isdigit() else 0
                        unplaced_int = int(cell_texts[data_start + 4]) if len(cell_texts) > data_start + 4 and cell_texts[data_start + 4].isdigit() else 0
                        
                        result["season_performance"].append({
                            "season": season,
                            "starts": starts_int,
                            "win": win_int,
                            "second": second_int,
                            "third": third_int,
                            "unplaced": unplaced_int
                        })
                        
                        # Accumulate season totals
                        season_totals["starts"] += starts_int
                        season_totals["win"] += win_int
                        season_totals["second"] += second_int
                        season_totals["third"] += third_int
                        season_totals["unplaced"] += unplaced_int
            
            # Add total row to season_performance
            if result["season_performance"]:
                result["season_performance"].append({
                    "season": "total",
                    "starts": season_totals["starts"],
                    "win": season_totals["win"],
                    "second": season_totals["second"],
                    "third": season_totals["third"],
                    "unplaced": season_totals["unplaced"]
                })
            
        except Exception as e:
            logger.error(f"Error in _scrape_distance_stats: {e}")
        
        return result
    
    async def _scrape_workouts(self) -> List[Dict]:
        """Scrape workout/gallop records"""
        workouts = []
        try:
            tables = await self.page.query_selector_all("table")
            for table in tables:
                table_id = await table.get_attribute("id") or ""
                class_name = await table.get_attribute("class") or ""
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = await rows[0].inner_text()
                if "晨操" in header or "日期" in header or "時間" in header:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 2:
                            workout = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            }
                            if workout.get("date"):
                                workouts.append(workout)
                    if workouts:
                        break
        except Exception as e:
            logger.error(f"Error in _scrape_workouts: {e}")
        return workouts
    
    async def _scrape_medical(self) -> List[Dict]:
        """Scrape medical/vet records"""
        records = []
        try:
            tables = await self.page.query_selector_all("table")
            for table in tables:
                table_id = await table.get_attribute("id") or ""
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = await rows[0].inner_text()
                if "傷患" in header or "日期" in header or "傷勢" in header or "病情" in header:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 2:
                            record = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            }
                            if record.get("date"):
                                records.append(record)
                    if records:
                        break
        except Exception as e:
            logger.error(f"Error in _scrape_medical: {e}")
        return records
    
    async def _scrape_movements(self) -> List[Dict]:
        """Scrape movement/location changes"""
        movements = []
        try:
            tables = await self.page.query_selector_all("table")
            for table in tables:
                table_id = await table.get_attribute("id") or ""
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = await rows[0].inner_text()
                if "MovementRecord" in table_id or "搬遷" in header or "搬馬" in header:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 2:
                            movement = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                                "details": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            }
                            if movement.get("date"):
                                movements.append(movement)
                    if movements:
                        break
        except Exception as e:
            logger.error(f"Error in _scrape_movements: {e}")
        return movements
    
    async def _scrape_overseas(self) -> List[Dict]:
        """Scrape overseas race records"""
        races = []
        try:
            tables = await self.page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 6:
                        race = {
                            "hkjc_horse_id": self.hkjc_horse_id,
                            "date": (await cells[0].inner_text()).strip() if len(cells) > 0 else "",
                            "country": (await cells[1].inner_text()).strip() if len(cells) > 1 else "",
                            "racecourse": (await cells[2].inner_text()).strip() if len(cells) > 2 else "",
                            "position": (await cells[3].inner_text()).strip() if len(cells) > 3 else "",
                            "distance": (await cells[4].inner_text()).strip() if len(cells) > 4 else "",
                            "prize": (await cells[5].inner_text()).strip() if len(cells) > 5 else "",
                        }
                        if race.get("date"):
                            races.append(race)
        except Exception as e:
            logger.error(f"Error in _scrape_overseas: {e}")
        return races
    
    async def _scrape_pedigree(self) -> Dict:
        """Scrape pedigree info"""
        pedigree = {"hkjc_horse_id": self.hkjc_horse_id}
        try:
            text = await self.page.inner_text("body")
            sire_match = re.search(r'父系\s*[:：]\s*([^\n]+)', text)
            dam_match = re.search(r'母系\s*[:：]\s*([^\n]+)', text)
            damsire_match = re.search(r'外祖父\s*[:：]\s*([^\n]+)', text)
            if sire_match:
                pedigree["sire"] = sire_match.group(1).strip()
            if dam_match:
                pedigree["dam"] = dam_match.group(1).strip()
            if damsire_match:
                pedigree["damsire"] = damsire_match.group(1).strip()
        except Exception as e:
            logger.error(f"Error in _scrape_pedigree: {e}")
        return pedigree
    
    async def save_to_mongodb(self, data: Dict):
        """Save all scraped data to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        hkjc_id = data["hkjc_horse_id"]
        
        # Save other collections as before
        collections_data = {
            "horse_race_history": data.get("race_history", []),
            "horse_workouts": data.get("workouts", []),
            "horse_medical": data.get("medical", []),
            "horse_movements": data.get("movements", []),
            "horse_overseas": data.get("overseas", []),
        }
        
        for collection_name, items in collections_data.items():
            if items:
                deleted = db.db[collection_name].delete_many({"hkjc_horse_id": hkjc_id}).deleted_count
                if isinstance(items, list) and len(items) > 0:
                    db.db[collection_name].insert_many(items)
                    print(f"   ✅ {collection_name}: {len(items)} records")
        
        # Save distance_stats as a single document with the new format
        if data.get("distance_stats"):
            db.db["horse_distance_stats"].delete_many({"hkjc_horse_id": hkjc_id})
            db.db["horse_distance_stats"].insert_one(data["distance_stats"])
            
            ds = data["distance_stats"]
            venue_count = len(ds.get("venue_performance", []))
            dist_count = len(ds.get("distance_performance", []))
            season_count = len(ds.get("season_performance", []))
            print(f"   ✅ horse_distance_stats: venue={venue_count}, distance={dist_count}, seasons={season_count}")
        
        # Update pedigree
        if data.get("pedigree"):
            db.db["horse_pedigree"].update_one(
                {"hkjc_horse_id": hkjc_id},
                {"$set": data["pedigree"]},
                upsert=True
            )
            print(f"   ✅ horse_pedigree: updated")
        
        db.disconnect()
        print("\n✅ All data saved!")


async def main():
    """Test the scraper"""
    scraper = HorseAllTabsScraper(headless=True, delay=3)
    
    async with scraper:
        hkjc_id = "HK_2023_J256"
        
        print(f"🚀 Testing complete scraper for: {hkjc_id}")
        
        try:
            data = await scraper.scrape_horse(hkjc_id)
            
            print("\n" + "=" * 80)
            print("📊 SCRAPE COMPLETE - Summary")
            print("=" * 80)
            
            for key, value in data.items():
                if key not in ["hkjc_horse_id", "url", "scraped_at"]:
                    if isinstance(value, list):
                        print(f"  {key}: {len(value)} records")
                    elif isinstance(value, dict):
                        if "error" in value:
                            print(f"  {key}: ⚠️  Error - {value['error']}")
                        else:
                            print(f"  {key}: ✓ data scraped")
            
            # Show distance stats format
            if data.get("distance_stats"):
                import json
                print("\n📊 Distance Stats Format:")
                print(json.dumps(data["distance_stats"], ensure_ascii=False, indent=2)[:1500])
            
            # Save to MongoDB
            await scraper.save_to_mongodb(data)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
