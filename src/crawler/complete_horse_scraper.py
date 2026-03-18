"""
Complete Horse Detail Scraper
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


class CompleteHorseScraper:
    """Complete scraper for all horse detail tabs"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
        self.db = None
    
    async def scrape_horse_complete(self, hkjc_horse_id: str) -> Dict:
        """
        Scrape all data for a horse
        
        Args:
            hkjc_horse_id: e.g., "HK_2023_J256"
            
        Returns:
            Dict with all scraped data
        """
        url = f"{self.BASE_URL}?horseid={hkjc_horse_id}"
        
        print(f"🐴 Starting complete scrape for: {hkjc_horse_id}")
        print("=" * 70)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(5000)
                
                result = {
                    "hkjc_horse_id": hkjc_horse_id,
                    "scraped_at": datetime.now().isoformat(),
                    "url": url
                }
                
                # 1. Basic Info (default page)
                print("\n📋 1. Extracting Basic Info...")
                result["basic_info"] = await self._extract_basic_info(page)
                print(f"   ✅ Name: {result['basic_info'].get('name', 'N/A')}")
                
                # 2. Race History with full details
                print("\n📊 2. Extracting Race History...")
                result["race_history"] = await self._extract_race_history_complete(page)
                print(f"   ✅ {len(result['race_history'])} races found")
                
                # 3. Distance Analysis (所跑途程)
                print("\n🏃 3. Extracting Distance Analysis...")
                result["distance_stats"] = await self._extract_distance_stats(page)
                print(f"   ✅ Distance stats extracted")
                
                # 4. Workouts (晨操紀錄)
                print("\n🌅 4. Extracting Workouts...")
                result["workouts"] = await self._extract_workouts(page)
                print(f"   ✅ {len(result['workouts'])} workouts found")
                
                # 5. Medical Records (傷患紀錄)
                print("\n🏥 5. Extracting Medical Records...")
                result["medical"] = await self._extract_medical(page)
                print(f"   ✅ {len(result['medical'])} medical records")
                
                # 6. Movements (搬遷紀錄)
                print("\n🚚 6. Extracting Movements...")
                result["movements"] = await self._extract_movements(page)
                print(f"   ✅ {len(result['movements'])} movement records")
                
                # 7. Overseas Records (海外賽績)
                print("\n🌍 7. Extracting Overseas Records...")
                result["overseas"] = await self._extract_overseas(page)
                print(f"   ✅ {len(result['overseas'])} overseas races")
                
                # 8. Jersey (彩衣)
                print("\n👕 8. Extracting Jersey...")
                result["jersey"] = await self._extract_jersey(page)
                print(f"   ✅ Jersey info extracted")
                
                # 9. Rating Result Weight (評分/體重/名次) - Separate page
                print("\n📈 9. Extracting Rating/Weight History...")
                result["ratings"] = await self._extract_rating_weight_history(page, hkjc_horse_id)
                print(f"   ✅ {len(result.get('ratings', []))} rating records")
                
                # Save to MongoDB
                await self._save_to_mongodb(result)
                
                await browser.close()
                return result
                
            except Exception as e:
                logger.error(f"Error scraping horse {hkjc_horse_id}: {e}")
                await browser.close()
                raise
    
    async def _extract_basic_info(self, page: Page) -> Dict:
        """Extract basic horse info"""
        text = await page.inner_text("body")
        content = await page.content()
        
        info = {}
        
        # Horse name from title or page
        title_match = re.search(r'<h1[^>]*>(.+?)</h1>', content, re.DOTALL)
        if title_match:
            info["name"] = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()
        
        # Extract using patterns
        patterns = {
            "country": r'出生地\s*/\s*馬齡\s*[:：]\s*([^/\n]+)',
            "age": r'出生地\s*/\s*馬齡\s*[:：\s]*[^/]+\s*/\s*(\d+)',
            "color": r'毛色\s*/\s*性別\s*[:：]\s*([^/\n]+)',
            "sex": r'毛色\s*/\s*性別\s*[:：\s]*[^/]+/\s*([^\n]+)',
            "import_type": r'進口類別\s*[:：]\s*([^\n]+)',
            "trainer": r'練馬師\s*[:：]\s*([^\n]+)',
            "owner": r'馬主\s*[:：]\s*([^\n]+)',
            "current_location": r'現在位置\s*\(\s*到達日期\s*\)\s*[:：\s]*([^\n(]+)',
            "arrival_date": r'現在位置.*?(\d{2}/\d{2}/\d{4})',
            "import_date": r'進口日期\s*[:：]\s*(\d{2}/\d{2}/\d{4})',
            "current_rating": r'現時評分\s*[:：]\s*(\d+)',
            "initial_rating": r'季初評分\s*[:：]\s*(\d+)',
            "sire": r'父系\s*[:：]\s*([^\n]+)',
            "dam": r'母系\s*[:：]\s*([^\n]+)',
            "damsire": r'外祖父\s*[:：]\s*([^\n]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                if key in ["age", "current_rating", "initial_rating"]:
                    value = int(value)
                info[key] = value
        
        # Career stats
        stats_match = re.search(r'冠\s*-\s*亞\s*-\s*季\s*-\s*總出賽次數.*?[:：]\s*(\d+)-(\d+)-(\d+)-(\d+)', text)
        if stats_match:
            info["career_wins"] = int(stats_match.group(1))
            info["career_seconds"] = int(stats_match.group(2))
            info["career_thirds"] = int(stats_match.group(3))
            info["career_starts"] = int(stats_match.group(4))
        
        return info
    
    async def _extract_race_history_complete(self, page: Page) -> List[Dict]:
        """Extract complete race history with rating/weight/position"""
        races = []
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            if len(rows) < 5:
                continue
            
            # Check header for race history indicators
            header_cells = await rows[0].query_selector_all("th, td")
            header_text = " ".join([await c.inner_text() for c in header_cells[:5]])
            
            if any(k in header_text for k in ["場次", "評分", "體重", "名次", "日期"]):
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 10:
                        race = {
                            "race_date": await cells[0].inner_text() if len(cells) > 0 else "",
                            "racecourse": await cells[1].inner_text() if len(cells) > 1 else "",
                            "race_no": await cells[2].inner_text() if len(cells) > 2 else "",
                            "race_class": await cells[3].inner_text() if len(cells) > 3 else "",
                            "distance": await cells[4].inner_text() if len(cells) > 4 else "",
                            "track_condition": await cells[5].inner_text() if len(cells) > 5 else "",
                            "position": await cells[6].inner_text() if len(cells) > 6 else "",
                            "rating": await cells[7].inner_text() if len(cells) > 7 else "",
                            "weight": await cells[8].inner_text() if len(cells) > 8 else "",
                            "jockey": await cells[9].inner_text() if len(cells) > 9 else "",
                            "odds": await cells[10].inner_text() if len(cells) > 10 else "",
                        }
                        races.append(race)
        
        return races
    
    async def _extract_distance_stats(self, page: Page) -> List[Dict]:
        """Extract distance analysis (所跑途程賽績紀錄)
        
        Returns:
            List of dicts aggregated by track + distance:
            [
                {
                    "course_type": "沙田草地",
                    "distance": "1400米",
                    "total_runs": 3,
                    "first": 0,
                    "second": 0,
                    "third": 1,
                    "others": 2
                },
                ...
            ]
        """
        import re
        
        # Aggregate data by course_type + distance
        aggregate = {}
        
        # Find tables with distance data
        tables = await page.query_selector_all("table")
        
        for table_idx, table in enumerate(tables):
            text = await table.inner_text()
            
            # Look for table with distance data
            if re.search(r'\d{4}', text) and ('好' in text or '軟' in text or '快' in text):
                lines = text.split('\n')
                
                for line in lines:
                    parts = line.split('\t')
                    
                    if len(parts) >= 6:
                        try:
                            position = parts[1].strip()
                            
                            # Skip header lines
                            if not position.isdigit():
                                continue
                            
                            # Extract course type
                            course_match = re.search(r'(沙田|跑馬地)(草地|泥地)?', line)
                            course_type = course_match.group(0) if course_match else "未知"
                            
                            # Extract distance
                            dist_match = re.search(r'(\d{4})\s+(好|快地|軟|快)', line)
                            if not dist_match:
                                continue
                            distance = dist_match.group(1)
                            
                            # Create key
                            key = f"{course_type}_{distance}"
                            
                            if key not in aggregate:
                                aggregate[key] = {
                                    "course_type": course_type,
                                    "distance": f"{distance}米",
                                    "total_runs": 0,
                                    "first": 0,
                                    "second": 0,
                                    "third": 0,
                                    "others": 0
                                }
                            
                            # Update counts
                            aggregate[key]["total_runs"] += 1
                            
                            pos = int(position)
                            if pos == 1:
                                aggregate[key]["first"] += 1
                            elif pos == 2:
                                aggregate[key]["second"] += 1
                            elif pos == 3:
                                aggregate[key]["third"] += 1
                            else:
                                aggregate[key]["others"] += 1
                                
                        except (ValueError, IndexError):
                            continue
        
        return list(aggregate.values())
    
    async def _extract_workouts(self, page: Page) -> List[Dict]:
        """Extract workout records"""
        workouts = []
        tables = await page.query_selector_all("table")
        
        for table in tables:
            rows = await table.query_selector_all("tr")
            for row in rows[1:]:
                cells = await row.query_selector_all("td")
                if len(cells) >= 5:
                    workouts.append({
                        "date": await cells[0].inner_text(),
                        "venue": await cells[1].inner_text(),
                        "distance": await cells[2].inner_text(),
                        "time": await cells[3].inner_text(),
                        "rider": await cells[4].inner_text(),
                    })
        
        return workouts
    
    async def _extract_medical(self, page: Page) -> List[Dict]:
        """Extract medical/vet records"""
        records = []
        text = await page.inner_text("body")
        
        # Look for injury records
        if "傷患" in text:
            # Try to find medical records table or section
            tables = await page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        records.append({
                            "date": await cells[0].inner_text(),
                            "issue": await cells[1].inner_text(),
                            "treatment": await cells[2].inner_text() if len(cells) > 2 else "",
                        })
        
        return records
    
    async def _extract_movements(self, page: Page) -> List[Dict]:
        """Extract movement/relocation records"""
        movements = []
        text = await page.inner_text("body")
        
        if "搬遷" in text or "從化" in text:
            tables = await page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 3:
                        movements.append({
                            "date": await cells[0].inner_text(),
                            "from": await cells[1].inner_text(),
                            "to": await cells[2].inner_text(),
                            "reason": await cells[3].inner_text() if len(cells) > 3 else "",
                        })
        
        return movements
    
    async def _extract_overseas(self, page: Page) -> List[Dict]:
        """Extract overseas race records"""
        races = []
        text = await page.inner_text("body")
        
        if "海外" in text:
            tables = await page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 6:
                        races.append({
                            "date": await cells[0].inner_text(),
                            "country": await cells[1].inner_text(),
                            "racecourse": await cells[2].inner_text(),
                            "position": await cells[3].inner_text(),
                            "distance": await cells[4].inner_text(),
                            "prize": await cells[5].inner_text(),
                        })
        
        return races
    
    async def _extract_jersey(self, page: Page) -> Dict:
        """Extract jersey/silk information"""
        jersey = {}
        
        try:
            # Look for jersey image
            images = await page.query_selector_all("img")
            for img in images:
                alt = await img.get_attribute("alt")
                src = await img.get_attribute("src")
                if alt and ("彩衣" in alt or "jersey" in alt.lower() or "silk" in alt.lower()):
                    jersey["image_url"] = src
                    break
            
            # Look for color description
            text = await page.inner_text("body")
            color_match = re.search(r'彩衣顏色\s*[:：]\s*([^\n]+)', text)
            if color_match:
                jersey["color_description"] = color_match.group(1).strip()
        
        except Exception as e:
            logger.warning(f"Error extracting jersey: {e}")
        
        return jersey
    
    async def _extract_rating_weight_history(self, page: Page, hkjc_horse_id: str) -> List[Dict]:
        """
        Extract rating/weight history from separate page.
        URL: https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid=HK_xxx
        
        This page has transposed table format:
        - Each column = one race
        - Rows contain: date, rating, result, weight, venue, track_type, distance, course, condition, class
        """
        ratings = []
        MIN_ROWS_FOR_RATING_TABLE = 10
        
        # Store the main horse URL before navigation
        main_horse_url = page.url
        
        try:
            # Navigate to rating result weight page
            rating_url = f"https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid={hkjc_horse_id}"
            logger.info(f"      Fetching rating history: {rating_url}")
            await page.goto(rating_url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(self.delay * 1000)
            
            tables = await page.query_selector_all("table")
            
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < MIN_ROWS_FOR_RATING_TABLE:
                    continue
                
                # Check if this is the rating table - look at row 2 for "評分"
                if len(rows) > 2:
                    row2_text = await rows[2].inner_text()
                    if "評分" not in row2_text:
                        continue
                else:
                    continue
                
                # Get number of columns (data columns, skip first header column)
                first_data_row = await rows[1].query_selector_all("td")
                num_cols = len(first_data_row)
                if num_cols <= 1:
                    continue
                
                logger.info(f"      Found rating table with {num_cols} columns")
                
                # Pre-fetch all cells for efficiency (outside loop)
                date_cells = await rows[1].query_selector_all("td")
                rating_cells = await rows[2].query_selector_all("td")
                result_cells = await rows[3].query_selector_all("td")
                weight_cells = await rows[4].query_selector_all("td")
                venue_cells = await rows[5].query_selector_all("td")
                track_type_cells = await rows[6].query_selector_all("td")
                distance_cells = await rows[7].query_selector_all("td")
                course_cells = await rows[8].query_selector_all("td")
                condition_cells = await rows[9].query_selector_all("td")
                class_cells = await rows[10].query_selector_all("td")
                
                # Extract columns (each column is a race)
                for col_idx in range(1, num_cols):
                    try:
                        # Extract date
                        date = (await date_cells[col_idx].inner_text()).strip() if col_idx < len(date_cells) else ""
                        if not date:
                            continue
                        
                        # Parse date format: "11/02/2026" -> "2026-02-11"
                        date_parts = date.split("/")
                        if len(date_parts) == 3:
                            formatted_date = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
                        else:
                            formatted_date = date
                        
                        # Parse rating
                        rating_str = (await rating_cells[col_idx].inner_text()).strip() if col_idx < len(rating_cells) else "0"
                        try:
                            rating = int(rating_str)
                        except ValueError:
                            rating = 0
                        
                        # Parse result (position)
                        result = (await result_cells[col_idx].inner_text()).strip() if col_idx < len(result_cells) else ""
                        
                        # Parse weight
                        weight_str = (await weight_cells[col_idx].inner_text()).strip() if col_idx < len(weight_cells) else "0"
                        try:
                            weight = int(weight_str)
                        except ValueError:
                            weight = 0
                        
                        # Parse venue
                        venue = (await venue_cells[col_idx].inner_text()).strip() if col_idx < len(venue_cells) else ""
                        
                        # Parse track type
                        track_type = (await track_type_cells[col_idx].inner_text()).strip() if col_idx < len(track_type_cells) else ""
                        
                        # Parse distance
                        dist_str = (await distance_cells[col_idx].inner_text()).strip() if col_idx < len(distance_cells) else "0"
                        try:
                            distance = int(dist_str)
                        except ValueError:
                            distance = 0
                        
                        # Parse course
                        course = (await course_cells[col_idx].inner_text()).strip() if col_idx < len(course_cells) else ""
                        
                        # Parse track condition
                        condition = (await condition_cells[col_idx].inner_text()).strip() if col_idx < len(condition_cells) else ""
                        
                        # Parse race class
                        class_str = (await class_cells[col_idx].inner_text()).strip() if col_idx < len(class_cells) else ""
                        try:
                            race_class = int(class_str) if class_str.isdigit() else 0
                        except ValueError:
                            race_class = 0
                        
                        record = {
                            "hkjc_horse_id": hkjc_horse_id,
                            "date": formatted_date,
                            "rating": rating,
                            "result": result,
                            "weight": weight,
                            "venue": venue,
                            "track_type": track_type,
                            "distance": distance,
                            "course": course,
                            "track_condition": condition,
                            "race_class": race_class
                        }
                        ratings.append(record)
                        
                    except Exception as e:
                        logger.warning(f"Error extracting rating column {col_idx}: {e}")
                        continue
            
            # Go back to main horse page for next extraction
            try:
                main_url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={hkjc_horse_id}"
                await page.goto(main_url, wait_until="domcontentloaded")
                await asyncio.sleep(self.delay)
            except Exception as e:
                logger.warning(f"Failed to navigate back to main horse page: {e}")
            
        except Exception as e:
            logger.warning(f"Error extracting rating weight history: {e}")
        
        return ratings
    
    async def _save_to_mongodb(self, data: Dict):
        """Save all data to appropriate collections"""
        print("\n💾 Saving to MongoDB...")
        
        self.db = DatabaseConnection()
        if not self.db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        hkjc_id = data["hkjc_horse_id"]
        
        # 1. Update/Insert basic horse info
        basic = data.get("basic_info", {})
        self.db.horses.update_one(
            {"hkjc_horse_id": hkjc_id},
            {"$set": {
                "hkjc_horse_id": hkjc_id,
                "name": basic.get("name"),
                "country": basic.get("country"),
                "age": basic.get("age"),
                "sex": basic.get("sex"),
                "color": basic.get("color"),
                "trainer": basic.get("trainer"),
                "owner": basic.get("owner"),
                "current_rating": basic.get("current_rating"),
                "initial_rating": basic.get("initial_rating"),
                "pedigree": {
                    "sire": basic.get("sire"),
                    "dam": basic.get("dam"),
                    "damsire": basic.get("damsire")
                },
                "last_updated": datetime.now().isoformat()
            }},
            upsert=True
        )
        print("   ✅ Basic info updated")
        
        # 2. Insert race history
        if data.get("race_history"):
            self.db.db["horse_race_history"].delete_many({"hkjc_horse_id": hkjc_id})
            for race in data["race_history"]:
                race["hkjc_horse_id"] = hkjc_id
                race["scraped_at"] = data["scraped_at"]
            self.db.db["horse_race_history"].insert_many(data["race_history"])
            print(f"   ✅ {len(data['race_history'])} races saved")
        
        # 3. Save workouts
        if data.get("workouts"):
            self.db.db["horse_workouts"].delete_many({"hkjc_horse_id": hkjc_id})
            for w in data["workouts"]:
                w["hkjc_horse_id"] = hkjc_id
                w["scraped_at"] = data["scraped_at"]
            self.db.db["horse_workouts"].insert_many(data["workouts"])
            print(f"   ✅ {len(data['workouts'])} workouts saved")
        
        # 4. Save medical records
        if data.get("medical"):
            self.db.db["horse_medical"].delete_many({"hkjc_horse_id": hkjc_id})
            for m in data["medical"]:
                m["hkjc_horse_id"] = hkjc_id
                m["scraped_at"] = data["scraped_at"]
            self.db.db["horse_medical"].insert_many(data["medical"])
            print(f"   ✅ {len(data['medical'])} medical records saved")
        
        # 5. Save movements
        if data.get("movements"):
            self.db.db["horse_movements"].delete_many({"hkjc_horse_id": hkjc_id})
            for m in data["movements"]:
                m["hkjc_horse_id"] = hkjc_id
                m["scraped_at"] = data["scraped_at"]
            self.db.db["horse_movements"].insert_many(data["movements"])
            print(f"   ✅ {len(data['movements'])} movements saved")
        
        # 6. Save overseas records
        if data.get("overseas"):
            self.db.db["horse_overseas"].delete_many({"hkjc_horse_id": hkjc_id})
            for o in data["overseas"]:
                o["hkjc_horse_id"] = hkjc_id
                o["scraped_at"] = data["scraped_at"]
            self.db.db["horse_overseas"].insert_many(data["overseas"])
            print(f"   ✅ {len(data['overseas'])} overseas records saved")
        
        # 7. Save distance stats
        if data.get("distance_stats"):
            self.db.db["horse_distance_stats"].update_one(
                {"hkjc_horse_id": hkjc_id},
                {"$set": {
                    "hkjc_horse_id": hkjc_id,
                    "distance_performance": data["distance_stats"],
                    "modified_at": data["scraped_at"]
                }},
                upsert=True
            )
            print("   ✅ Distance stats saved")
        
        # 8. Save jersey info
        if data.get("jersey"):
            self.db.db["horse_jerseys"].update_one(
                {"hkjc_horse_id": hkjc_id},
                {"$set": {
                    "hkjc_horse_id": hkjc_id,
                    **data["jersey"],
                    "updated_at": data["scraped_at"]
                }},
                upsert=True
            )
            print("   ✅ Jersey info saved")
        
        # 9. Save ratings (評分/體重/名次歷史)
        if data.get("ratings"):
            self.db.db["horse_ratings"].delete_many({"hkjc_horse_id": hkjc_id})
            for rating in data["ratings"]:
                rating["scraped_at"] = data["scraped_at"]
            self.db.db["horse_ratings"].insert_many(data["ratings"])
            print(f"   ✅ {len(data['ratings'])} rating records saved")
        
        self.db.disconnect()
        print("\n✅ All data saved successfully!")


async def main():
    """Test the complete scraper"""
    scraper = CompleteHorseScraper(headless=True, delay=3)
    
    # Test with 祝願
    hkjc_id = "HK_2023_J256"
    
    result = await scraper.scrape_horse_complete(hkjc_id)
    
    print("\n" + "=" * 70)
    print("📊 SCRAPE COMPLETE!")
    print("=" * 70)
    print(f"Horse: {result['basic_info'].get('name')}")
    print(f"Total races: {len(result.get('race_history', []))}")
    print(f"Total workouts: {len(result.get('workouts', []))}")
    print(f"Medical records: {len(result.get('medical', []))}")
    print(f"Movements: {len(result.get('movements', []))}")
    print(f"Overseas races: {len(result.get('overseas', []))}")


if __name__ == "__main__":
    asyncio.run(main())
