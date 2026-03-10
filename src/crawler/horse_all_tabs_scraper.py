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
    Scrapes: race_history, distance_stats, workouts, medical, movements, overseas, jersey, rating
    """
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    RATING_URL = "https://racing.hkjc.com/zh-hk/local/information/ratingresultweight"
    VETERINARY_URL = "https://racing.hkjc.com/zh-hk/local/information/veterinaryrecord"
    MOVEMENT_URL = "https://racing.hkjc.com/zh-hk/local/information/movementrecords"
    
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
            
            # Scrape horse ratings from ratingresultweight page
            print("\n📊 RATINGS. Scraping 馬匹評分/體重/名次...")
            try:
                result["horse_ratings"] = await self._scrape_ratings()
                print(f"   ✅ {len(result['horse_ratings'])} scraped")
            except Exception as e:
                logger.error(f"Error scraping ratings: {e}")
                result["horse_ratings"] = []
            
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
        """Scrape race history table with new format"""
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
                    
                    # Find column indices
                    col_idx = {}
                    for i, h in enumerate(headers):
                        h_clean = h.strip()
                        if "場次" in h_clean:
                            col_idx["race_number"] = i
                        elif "名次" in h_clean:
                            col_idx["rank"] = i
                        elif "日期" in h_clean:
                            col_idx["date"] = i
                        elif "馬場" in h_clean or "跑道" in h_clean:
                            col_idx["track_condition"] = i
                        elif "途程" in h_clean:
                            col_idx["distance"] = i
                        elif "場地狀況" in h_clean or "場地" in h_clean:
                            col_idx["going"] = i
                        elif "賽事班次" in h_clean or "班次" in h_clean:
                            col_idx["race_class"] = i
                        elif "檔位" in h_clean:
                            col_idx["draw"] = i
                        elif "評分" in h_clean:
                            col_idx["rating"] = i
                        elif "練馬師" in h_clean:
                            col_idx["trainer"] = i
                        elif "騎師" in h_clean:
                            col_idx["jockey"] = i
                        elif "頭馬距離" in h_clean:
                            col_idx["finish_distance"] = i
                        elif "獨贏" in h_clean:
                            col_idx["win_odds"] = i
                        elif "實際負磅" in h_clean:
                            col_idx["actual_weight"] = i
                        elif "沿途走位" in h_clean:
                            col_idx["running_position"] = i
                        elif "完成時間" in h_clean:
                            col_idx["finish_time"] = i
                        elif "排位體重" in h_clean or "體重" in h_clean:
                            col_idx["declared_weight"] = i
                        elif "配備" in h_clean:
                            col_idx["equipment"] = i
                    
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 10:
                            cell_texts = [(await c.inner_text()).strip() for c in cells]
                            
                            race_data = {"hkjc_horse_id": self.hkjc_horse_id}
                            
                            # Map to new keys
                            if "race_number" in col_idx and col_idx["race_number"] < len(cell_texts):
                                race_data["race_number"] = cell_texts[col_idx["race_number"]]
                            if "rank" in col_idx and col_idx["rank"] < len(cell_texts):
                                race_data["rank"] = cell_texts[col_idx["rank"]]
                            if "date" in col_idx and col_idx["date"] < len(cell_texts):
                                race_data["date"] = cell_texts[col_idx["date"]]
                            if "track_condition" in col_idx and col_idx["track_condition"] < len(cell_texts):
                                race_data["track_condition"] = cell_texts[col_idx["track_condition"]]
                            if "distance" in col_idx and col_idx["distance"] < len(cell_texts):
                                # Extract numeric distance
                                dist_str = cell_texts[col_idx["distance"]]
                                race_data["distance"] = int(dist_str) if dist_str.isdigit() else 0
                            if "going" in col_idx and col_idx["going"] < len(cell_texts):
                                race_data["going"] = cell_texts[col_idx["going"]]
                            if "race_class" in col_idx and col_idx["race_class"] < len(cell_texts):
                                class_str = cell_texts[col_idx["race_class"]]
                                race_data["race_class"] = int(class_str) if class_str.isdigit() else 0
                            if "draw" in col_idx and col_idx["draw"] < len(cell_texts):
                                draw_str = cell_texts[col_idx["draw"]]
                                race_data["draw"] = int(draw_str) if draw_str.isdigit() else 0
                            if "rating" in col_idx and col_idx["rating"] < len(cell_texts):
                                rating_str = cell_texts[col_idx["rating"]]
                                race_data["rating"] = int(rating_str) if rating_str.isdigit() else 0
                            if "trainer" in col_idx and col_idx["trainer"] < len(cell_texts):
                                race_data["trainer"] = cell_texts[col_idx["trainer"]]
                            if "jockey" in col_idx and col_idx["jockey"] < len(cell_texts):
                                race_data["jockey"] = cell_texts[col_idx["jockey"]]
                            if "finish_distance" in col_idx and col_idx["finish_distance"] < len(cell_texts):
                                race_data["finish_distance"] = cell_texts[col_idx["finish_distance"]]
                            if "win_odds" in col_idx and col_idx["win_odds"] < len(cell_texts):
                                odds_str = cell_texts[col_idx["win_odds"]].replace('$', '').replace(',', '')
                                race_data["win_odds"] = float(odds_str) if odds_str.replace('.', '').isdigit() else 0.0
                            if "actual_weight" in col_idx and col_idx["actual_weight"] < len(cell_texts):
                                weight_str = cell_texts[col_idx["actual_weight"]]
                                race_data["actual_weight"] = int(weight_str) if weight_str.isdigit() else 0
                            if "running_position" in col_idx and col_idx["running_position"] < len(cell_texts):
                                race_data["running_position"] = cell_texts[col_idx["running_position"]]
                            if "finish_time" in col_idx and col_idx["finish_time"] < len(cell_texts):
                                race_data["finish_time"] = cell_texts[col_idx["finish_time"]]
                            if "declared_weight" in col_idx and col_idx["declared_weight"] < len(cell_texts):
                                weight_str = cell_texts[col_idx["declared_weight"]]
                                race_data["declared_weight"] = int(weight_str) if weight_str.isdigit() else 0
                            if "equipment" in col_idx and col_idx["equipment"] < len(cell_texts):
                                race_data["equipment"] = cell_texts[col_idx["equipment"]]
                            
                            if race_data.get("date"):
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
        """Scrape medical/vet records using direct URL"""
        records = []
        try:
            # Use direct URL for veterinary records
            vet_url = f"{self.VETERINARY_URL}?horseid={self.hkjc_horse_id}"
            await self.page.goto(vet_url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            tables = await self.page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = await rows[0].inner_text()
                # Look for table with exact columns: 馬號, 馬名, 日期, 詳情 (skip 後備馬匹 table)
                if "馬號" in header and "馬名" in header and "日期" in header and "詳情" in header and "後備" not in header:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 4:
                            cell_texts = [(await c.inner_text()).strip() for c in cells]
                            # Skip empty rows and header-like rows
                            if not cell_texts[2] and not cell_texts[3]:
                                continue
                            
                            # Skip header-like rows (these are not real medical records)
                            date_value = cell_texts[2].strip() if len(cell_texts) > 2 else ""
                            if any(keyword in date_value for keyword in ['毛色', '性別', '出生', '進口', '獎金', '出賽', '位置', '練馬師', '馬名', '馬號', '總']):
                                continue
                            record = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "date": cell_texts[2] if len(cell_texts) > 2 else "",
                                "details": cell_texts[3] if len(cell_texts) > 3 else "",
                                "passed_date": cell_texts[4] if len(cell_texts) > 4 else ""
                            }
                            if record.get("date") or record.get("details"):
                                records.append(record)
                    break
        except Exception as e:
            logger.error(f"Error in _scrape_medical: {e}")
        return records
    
    async def _scrape_movements(self) -> List[Dict]:
        """Scrape movement/location changes using direct URL"""
        movements = []
        try:
            # Use direct URL for movement records
            movement_url = f"{self.MOVEMENT_URL}?horseid={self.hkjc_horse_id}"
            await self.page.goto(movement_url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            tables = await self.page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue
                header = await rows[0].inner_text()
                # Look for table with 從, 至, 到達日期 columns
                if "從" in header and "至" in header and "到達日期" in header:
                    for row in rows[1:]:
                        cells = await row.query_selector_all("td")
                        if len(cells) >= 3:
                            cell_texts = [(await c.inner_text()).strip() for c in cells]
                            # Skip empty rows
                            if not any(cell_texts):
                                continue
                            # Skip header-like rows (None, empty, or header keywords)
                            from_loc = cell_texts[0].strip() if len(cell_texts) > 0 else ""
                            to_loc = cell_texts[1].strip() if len(cell_texts) > 1 else ""
                            arrival = cell_texts[2].strip() if len(cell_texts) > 2 else ""
                            
                            # Skip if any cell contains "None" or is a header keyword
                            if from_loc in ["None", "none", ""] and to_loc in ["None", "none", ""]:
                                continue
                            if "從" in from_loc or "至" in from_loc or "從" in to_loc or "至" in to_loc:
                                continue
                            if arrival in ["None", "none", ""]:
                                continue
                            
                            movement = {
                                "hkjc_horse_id": self.hkjc_horse_id,
                                "from_location": from_loc,
                                "to_location": to_loc,
                                "arrival_date": arrival
                            }
                            if movement.get("from_location") or movement.get("to_location"):
                                movements.append(movement)
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
    
    async def _scrape_ratings(self) -> List[Dict]:
        """Scrape horse ratings from ratingresultweight page"""
        ratings = []
        try:
            rating_url = f"https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid={self.hkjc_horse_id}"
            await self.page.goto(rating_url, wait_until="networkidle")
            await self.page.wait_for_timeout(self.delay * 1000)
            
            tables = await self.page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 10:
                    continue
                
                # Check if this is the rating table - look at row 2 which should have "評分"
                if len(rows) <= 2:
                    continue
                row2_cells = await rows[2].query_selector_all("td, th")
                if len(row2_cells) == 0:
                    continue
                row2_first = await row2_cells[0].inner_text()
                if "評分" not in row2_first:
                    continue
                
                # Get number of columns (races)
                first_data_row = await rows[1].query_selector_all("td")
                num_cols = len(first_data_row)
                
                for col_idx in range(1, num_cols):
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
                        
                        # Parse fields
                        distance_str = (await distance_cells[col_idx].inner_text()).strip() if col_idx < len(distance_cells) else "0"
                        class_str = (await class_cells[col_idx].inner_text()).strip() if col_idx < len(class_cells) else ""
                        weight_str = (await weight_cells[col_idx].inner_text()).strip() if col_idx < len(weight_cells) else "0"
                        rating_str = (await rating_cells[col_idx].inner_text()).strip() if col_idx < len(rating_cells) else "0"
                        
                        try:
                            distance = int(distance_str)
                        except:
                            distance = 0
                        
                        try:
                            race_class = int(class_str)
                        except:
                            race_class = 0
                        
                        try:
                            horse_weight = int(weight_str)
                        except:
                            horse_weight = 0
                        
                        try:
                            rating = int(rating_str)
                        except:
                            rating = 0
                        
                        record = {
                            "hkjc_horse_id": self.hkjc_horse_id,
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
                        
                        ratings.append(record)
                    except Exception as e:
                        continue
                
                break
        except Exception as e:
            logger.error(f"Error in _scrape_ratings: {e}")
        return ratings
    
    async def _scrape_pedigree(self) -> Dict:
        """Scrape pedigree info - just get URL"""
        pedigree = {"hkjc_horse_id": self.hkjc_horse_id}
        try:
            # Get current URL after clicking pedigree tab
            pedigree["pedigree_url"] = self.page.url if self.page else ""
            
            # Also try to extract pedigree text
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
        # Add pedigree_url to horses collection
        if data.get("pedigree"):
            pedigree_data = data["pedigree"]
            pedigree_url = pedigree_data.get("pedigree_url", "")
            
            # Update horses collection with pedigree info
            if pedigree_url:
                db.db["horses"].update_one(
                    {"hkjc_horse_id": hkjc_id},
                    {"$set": {"pedigree_url": pedigree_url}},
                    upsert=True
                )
                print(f"   ✅ pedigree_url added to horses")
            
            # Also save to horse_pedigree for backward compatibility
            db.db["horse_pedigree"].update_one(
                {"hkjc_horse_id": hkjc_id},
                {"$set": pedigree_data},
                upsert=True
            )
        
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
