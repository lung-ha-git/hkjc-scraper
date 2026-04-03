"""
HKJC Horse Distance Performance Scraper
Extract distance performance from horse detail page
"""

import asyncio
import re
from playwright.async_api import async_playwright, Page
from typing import Dict, List, Optional


class HorseDistanceScraper:
    """Scraper for horse distance performance"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/horse"
    
    async def scrape_distance_performance(self, horse_id: str) -> List[Dict]:
        """Scrape distance performance for a horse
        
        Args:
            horse_id: HKJC horse ID
            
        Returns:
            List of dicts with distance performance data:
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
        url = f"{self.BASE_URL}?horseid={horse_id}"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
                
                # Extract distance stats using the same logic as complete_horse_scraper
                result = await self._extract_distance_stats(page)
                
                return result
                
            except Exception as e:
                print(f"Error scraping distance for {horse_id}: {e}")
                return []
            finally:
                await browser.close()
    
    async def _extract_distance_stats(self, page: Page) -> List[Dict]:
        """Extract distance analysis (所跑途程賽績紀錄)
        
        Returns:
            List of dicts aggregated by track + distance
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


async def test():
    """Test function"""
    scraper = HorseDistanceScraper()
    result = await scraper.scrape_distance_performance("HK_2025_L108")
    print("Distance Performance:")
    print(result)


if __name__ == "__main__":
    asyncio.run(test())
