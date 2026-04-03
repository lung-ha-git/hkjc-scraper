"""
HKJC Race Results Scraper
Scrape race results, payouts, and incidents from localresults page
"""

import asyncio
import re
from datetime import datetime
from playwright.async_api import async_playwright, Page
from typing import Dict, List, Optional
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from src.constants.payout_map import normalize_payout_keys


class RaceResultsScraper:
    """Scrape HKJC race results"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/localresults"
    
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
    
    async def scrape_race(self, race_date: str, racecourse: str, race_no: int) -> Dict:
        """
        Scrape race results for a specific race
        
        Args:
            race_date: Format YYYY/MM/DD (e.g., "2026/03/01")
            racecourse: ST (Sha Tin) or HV (Happy Valley)
            race_no: Race number (e.g., 7)
        
        Returns:
            Dict with race data
        """
        # Convert date format from YYYY/MM/DD to DD/MM/YYYY for HKJC URL
        if "/" in race_date:
            parts = race_date.split("/")
            date_ddmmyyyy = f"{parts[2]}/{parts[1]}/{parts[0]}"
        else:
            date_ddmmyyyy = race_date  # Already in correct format
        
        # Use lowercase params (racecourse=, raceno=) matching actual HKJC URL format
        url = f"{self.BASE_URL}?racedate={date_ddmmyyyy}&racecourse=&raceno={race_no}"
        
        print(f"\n🏇 Scraping: {race_date} {racecourse} Race {race_no}")
        print(f"URL: {url}")
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(self.delay)
            
            # Extract race metadata
            race_meta = await self._scrape_race_metadata(page, race_date, racecourse, race_no)
            
            # Extract results
            results = await self._scrape_results_table(page)
            
            # Extract payouts
            payouts = await self._scrape_payouts_table(page)
            
            # Extract incidents
            incidents = await self._scrape_incidents_table(page)
            
            await context.close()
            
            return {
                "race_date": race_date,
                "racecourse": racecourse,
                "race_no": race_no,
                "race_id": race_meta.get("race_id"),
                "metadata": race_meta,
                "results": results,
                "payout": payouts,  # normalized to English keys
                "incidents": incidents,
                "scraped_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Error scraping race: {e}")
            await context.close()
            raise
    
    async def _scrape_race_metadata(self, page: Page, race_date: str, racecourse: str, race_no: int) -> Dict:
        """Scrape race metadata from page"""
        meta = {
            "race_date": race_date,
            "racecourse": racecourse,
            "race_no": race_no,
            "venue": racecourse,
        }
        
        try:
            text = await page.inner_text("body")
            
            # Extract race info using regex
            # Example: "第 7 場 (481)"
            race_id_match = re.search(r'第\s*(\d+)\s*場\s*\((\d+)\)', text)
            if race_id_match:
                meta["race_no_display"] = int(race_id_match.group(1))
                meta["race_id_num"] = int(race_id_match.group(2))  # HKJC numeric ID
            
            # Race name and class
            # Example: "一級賽 - 2000米" and "花旗銀行香港金盃"
            race_name_match = re.search(r'([^-\n]+)\s*-\s*(\d+米)', text)
            if race_name_match:
                meta["race_name"] = race_name_match.group(1).strip()
                meta["distance"] = race_name_match.group(2).strip()
            
            # Class
            class_match = re.search(r'(一級賽|二級賽|三級賽|一班|二班|三班|四班|五班)', text)
            if class_match:
                meta["class"] = class_match.group(1)
            
            # Prize
            prize_match = re.search(r'HK\$([\d,]+)', text)
            if prize_match:
                meta["prize"] = f"HK${prize_match.group(1)}"
            
            # Track and condition
            # Example: "草地 - \"B+2\" 賽道"
            track_match = re.search(r'(草地|全天候跑道)\s*-\s*"?([^"]+)"?\s*賽道', text)
            if track_match:
                meta["course"] = track_match.group(1)
                meta["track"] = track_match.group(2)
            
            # Track condition
            condition_match = re.search(r'場地狀況\s*:\s*(\S+)', text)
            if condition_match:
                meta["track_condition"] = condition_match.group(1)
            
            # Sectional times
            # Example: "(25.65) (49.17) (1:13.13)"
            sectional_times = re.findall(r'\((\d+\.?\d*)\)', text)
            if sectional_times:
                meta["sectional_times"] = sectional_times
            
            return meta
            
        except Exception as e:
            print(f"Error scraping metadata: {e}")
            return meta
    
    async def _scrape_results_table(self, page: Page) -> List[Dict]:
        """Scrape race results table - class='f_tac table_bd draggable'"""
        results = []
        
        try:
            # Find the results table
            tables = await page.query_selector_all("table.f_tac.table_bd")
            
            for table in tables:
                # Check if this is the results table by looking at header
                header_row = await table.query_selector("tr")
                if not header_row:
                    continue
                
                header_text = await header_row.inner_text()
                
                # Results table should have columns like "名次", "馬號", "馬名"
                if "名次" not in header_text or "馬號" not in header_text:
                    continue
                
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) < 10:
                        continue
                    
                    # Extract data
                    position = await cells[0].inner_text()
                    horse_no = await cells[1].inner_text()
                    
                    # Horse name might have link
                    horse_link = await cells[2].query_selector("a")
                    if horse_link:
                        href = await horse_link.get_attribute("href")
                        horse_id_match = re.search(r'horseid=([^&]+)', href or "")
                        horse_id = horse_id_match.group(1) if horse_id_match else ""
                        horse_name = await horse_link.inner_text()
                    else:
                        horse_id = ""
                        horse_name = await cells[2].inner_text()
                    
                    # Continue with other fields
                    jockey = await cells[3].inner_text()
                    trainer = await cells[4].inner_text()
                    weight_carried = await cells[5].inner_text()
                    draw = await cells[6].inner_text()
                    distance = await cells[7].inner_text()
                    finish_time = await cells[8].inner_text()
                    odds = await cells[9].inner_text()
                    
                    # Clean up
                    result = {
                        "position": int(position) if position.isdigit() else position,
                        "horse_no": int(horse_no) if horse_no.isdigit() else horse_no,
                        "horse_id": horse_id,
                        "horse_name": horse_name.strip(),
                        "jockey": jockey.strip(),
                        "trainer": trainer.strip(),
                        "weight_carried": weight_carried.strip(),
                        "draw": draw.strip(),
                        "distance": distance.strip(),
                        "finish_time": finish_time.strip(),
                        "odds": odds.strip()
                    }
                    results.append(result)
                
                if results:
                    print(f"   ✅ Found {len(results)} horse results")
                    break
            
            return results
            
        except Exception as e:
            print(f"Error scraping results: {e}")
            return []
    
    async def _scrape_payouts_table(self, page: Page) -> Dict:
        """Scrape payouts table - class='table_bd f_tac f_fs13 f_fl'"""
        payouts = {}
        
        try:
            tables = await page.query_selector_all("table.table_bd.f_tac.f_fs13")
            
            for table in tables:
                header_text = await table.inner_text()
                if "派彩" not in header_text:
                    continue
                
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    
                    pool_name = await cells[0].inner_text()
                    combination = await cells[1].inner_text()
                    payout = await cells[2].inner_text()
                    
                    # Clean up
                    pool_name = pool_name.strip()
                    combination = combination.strip()
                    payout = payout.strip().replace("$", "").replace(",", "")
                    
                    if pool_name not in payouts:
                        payouts[pool_name] = {}
                    
                    payouts[pool_name][combination] = payout
                
                if payouts:
                    print(f"   ✅ Found {len(payouts)} payout pools")
                    break
            
            return normalize_payout_keys(payouts)
            
        except Exception as e:
            print(f"Error scraping payouts: {e}")
            return {}
    
    async def _scrape_incidents_table(self, page: Page) -> List[Dict]:
        """Scrape incidents table - class='f_tac table_bd'"""
        incidents = []
        
        try:
            tables = await page.query_selector_all("table.f_tac.table_bd")
            
            for table in tables:
                header_text = await table.inner_text()
                if "競賽事件報告" not in header_text:
                    continue
                
                rows = await table.query_selector_all("tr")
                
                for row in rows[1:]:  # Skip header
                    cells = await row.query_selector_all("td")
                    if len(cells) < 3:
                        continue
                    
                    position = await cells[0].inner_text()
                    horse_no = await cells[1].inner_text()
                    
                    # Horse name with link
                    horse_link = await cells[2].query_selector("a")
                    if horse_link:
                        href = await horse_link.get_attribute("href")
                        horse_id_match = re.search(r'horseid=([^&]+)', href or "")
                        horse_id = horse_id_match.group(1) if horse_id_match else ""
                        horse_name = await horse_link.inner_text()
                    else:
                        horse_id = ""
                        horse_name = await cells[2].inner_text()
                    
                    report = await cells[3].inner_text()
                    
                    incident = {
                        "position": int(position) if position.isdigit() else position,
                        "horse_no": int(horse_no) if horse_no.isdigit() else horse_no,
                        "horse_id": horse_id,
                        "horse_name": horse_name.strip(),
                        "report": report.strip()
                    }
                    incidents.append(incident)
                
                if incidents:
                    print(f"   ✅ Found {len(incidents)} incident reports")
                    break
            
            return incidents
            
        except Exception as e:
            print(f"Error scraping incidents: {e}")
            return []
    
    async def save_to_mongodb(self, race_data: Dict):
        """Save race data to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        race_id = f"{race_data['race_date']}_{race_data['racecourse']}_{race_data['race_no']}"
        
        # 1. Save race metadata
        race_doc = {
            "_id": race_id,
            **race_data["metadata"],
            "results_count": len(race_data["results"]),
            "scraped_at": race_data["scraped_at"]
        }
        db.db["races"].replace_one({"_id": race_id}, race_doc, upsert=True)
        print(f"   ✅ races: {race_id}")
        
        # 2. Save race results
        db.db["race_results"].delete_many({"race_id": race_id})
        for result in race_data["results"]:
            result["race_id"] = race_id
        if race_data["results"]:
            db.db["race_results"].insert_many(race_data["results"])
        print(f"   ✅ race_results: {len(race_data['results'])} records")
        
        # 3. Save payouts
        db.db["race_payouts"].replace_one(
            {"race_id": race_id},
            {"race_id": race_id, "pools": race_data["payout"], "scraped_at": race_data["scraped_at"]},
            upsert=True
        )
        print(f"   ✅ race_payouts: {len(race_data['payout'])} pools")
        
        # 4. Save incidents
        db.db["race_incidents"].delete_many({"race_id": race_id})
        for incident in race_data["incidents"]:
            incident["race_id"] = race_id
        if race_data["incidents"]:
            db.db["race_incidents"].insert_many(race_data["incidents"])
        print(f"   ✅ race_incidents: {len(race_data['incidents'])} records")
        
        db.disconnect()
        print("\n✅ All race data saved!")


async def main():
    """Test with race 2026/03/01 ST Race 7"""
    async with RaceResultsScraper(headless=True, delay=2) as scraper:
        # Test with known race
        race_data = await scraper.scrape_race("2026/03/01", "ST", 7)
        
        print("\n" + "=" * 80)
        print("📊 SCRAPED RACE DATA")
        print("=" * 80)
        
        print(f"\n🏇 Race: {race_data['metadata'].get('race_name', 'N/A')}")
        print(f"   Distance: {race_data['metadata'].get('distance', 'N/A')}")
        print(f"   Class: {race_data['metadata'].get('class', 'N/A')}")
        print(f"   Track: {race_data['metadata'].get('track', 'N/A')}")
        
        print(f"\n📋 Results: {len(race_data['results'])} horses")
        for r in race_data['results'][:3]:
            print(f"   {r['position']}. {r['horse_name']} ({r['horse_id']}) - {r['jockey']}")
        
        print(f"\n💰 Payouts: {len(race_data['payouts'])} pools")
        
        print(f"\n📝 Incidents: {len(race_data['incidents'])} reports")
        
        # Save to MongoDB
        await scraper.save_to_mongodb(race_data)


if __name__ == "__main__":
    asyncio.run(main())
