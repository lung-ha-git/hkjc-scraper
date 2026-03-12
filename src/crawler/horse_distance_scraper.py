"""
HKJC Horse Distance Performance Scraper
Extract distance performance from horse detail page
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import Dict, List, Optional


class HorseDistanceScraper:
    """Scraper for horse distance performance"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    async def scrape_distance_performance(self, horse_id: str) -> Dict:
        """Scrape distance performance for a horse
        
        Args:
            horse_id: HKJC horse ID
            
        Returns:
            Dict with distance performance data
        """
        url = f"{self.BASE_URL}?horseid={horse_id}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
                
                # Find the distance performance table
                # It's usually Table 8 or the table containing meters like 1000, 1200
                tables = await page.query_selector_all("table")
                
                distance_performance = {}
                
                for table_idx, table in enumerate(tables):
                    # Use inner_text() to preserve tabs
                    text = await table.inner_text()
                    
                    # Look for table with distance data (contains 4 digits like 1000, 1200, 2000)
                    if re.search(r'\d{4}', text) and ('好' in text or '軟' in text or '快' in text):
                        # Extract distance performance
                        dist_data = self._parse_distance_table(text)
                        if dist_data:
                            distance_performance.update(dist_data)
                
                return distance_performance
                
            except Exception as e:
                print(f"Error scraping distance for {horse_id}: {e}")
                return {}
            finally:
                await browser.close()
    
    def _parse_distance_table(self, text: str) -> Dict:
        """Parse distance performance from table text
        
        Format from HTML:
        452	12	19/02/26	沙田草地"A"	2000	好	3	10	79	游達榮	麥文堅	10-1/2	6.1	135	9 9 9 12 12	2.02.66	1068	XB/CP1/TT
        """
        result = {}
        
        lines = text.split('\n')
        
        # Track unique distances seen
        distances_seen = {}
        
        for line in lines:
            # Look for patterns like "2000好" (4 digits followed by track condition)
            matches = re.findall(r'(\d{4})\s+好', line)
            for distance in matches:
                if distance not in distances_seen:
                    distances_seen[distance] = 0
                distances_seen[distance] += 1
        
        # Convert to result format
        for distance, count in distances_seen.items():
            result[f"distance_{distance}"] = {
                "runs": count
            }
        
        return result


async def test():
    """Test function"""
    scraper = HorseDistanceScraper()
    result = await scraper.scrape_distance_performance("HK_2025_L108")
    print("Distance Performance:")
    print(result)


if __name__ == "__main__":
    asyncio.run(test())
