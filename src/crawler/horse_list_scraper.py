"""
HKJC Horse List Scraper
Scrape list of horses from selecthorse page

Entry point: https://racing.hkjc.com/zh-hk/local/information/selecthorse
Filters: 馬名字數 (name length), 練馬師 (trainer), etc.

Output: List of HKJC horse IDs
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import List, Dict, Set
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class HorseListScraper:
    """Scraper to get horse list from HKJC selecthorse page"""
    
    BASE_URL = "https://racing.hkjc.com/zh-hk/local/information/selecthorse"
    
    def __init__(self, headless: bool = True):
        self.headless = headless
    
    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def get_all_horse_ids(self, name_length: str = None, trainer_id: str = None) -> List[Dict]:
        """
        Get all horse IDs from selecthorse page
        
        Args:
            name_length: Filter by name length (一字/二字/三字)
            trainer_id: Filter by trainer ID (e.g., "NM" for 廖康銘)
        
        Returns:
            List of dict with horse_id, horse_name, trainer, etc.
        """
        print("\n🐴 Getting horse list from HKJC...")
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        # Build URL with filters
        url = self.BASE_URL
        params = []
        if name_length:
            params.append(f"HorseNameLen={name_length}")
        if trainer_id:
            params.append(f"trainerid={trainer_id}")
        
        if params:
            url += "?" + "&".join(params)
        
        print(f"URL: {url}")
        
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            
            # Get all horse links
            horse_links = await self._extract_horse_links(page)
            
            await context.close()
            
            print(f"✅ Found {len(horse_links)} horses")
            return horse_links
            
        except Exception as e:
            print(f"Error: {e}")
            await context.close()
            raise
    
    async def _extract_horse_links(self, page) -> List[Dict]:
        """Extract horse links from page"""
        horses = []
        
        # Look for horse links
        links = await page.query_selector_all("a[href*='horse?horseid=']")
        
        seen_ids: Set[str] = set()
        
        for link in links:
            href = await link.get_attribute("href")
            horse_id_match = re.search(r'horseid=([^&]+)', href or "")
            
            if not horse_id_match:
                continue
            
            horse_id = horse_id_match.group(1)
            
            # Skip duplicates
            if horse_id in seen_ids:
                continue
            seen_ids.add(horse_id)
            
            # Get horse name from text
            horse_name = await link.inner_text()
            horse_name = horse_name.strip()
            
            if horse_name and not horse_name.startswith("/"):
                horses.append({
                    "horse_id": horse_id,
                    "horse_name": horse_name,
                    "url": href
                })
        
        return horses
    
    async def filter_by_name_length(self, name_length: str = "二字") -> List[Dict]:
        """Get horses filtered by name length"""
        print(f"\n🔍 Filtering by name length: {name_length}")
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            # Go to selecthorse
            await page.goto(self.BASE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Look for name length filter dropdown/options
            # The filter might be a dropdown or links
            
            # Try to find and click the name length filter
            # Common patterns: select dropdown, radio buttons, or links
            
            # First, let's try clicking on the name length option
            filter_option = None
            
            # Try different selectors
            selectors = [
                f"text={name_length}",
                f"a:text({name_length})",
                f"text=馬名字數",
            ]
            
            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        await element.click()
                        await asyncio.sleep(2)
                        print(f"Clicked: {selector}")
                        break
                except:
                    continue
            
            # Get filtered horse links
            horses = await self._extract_horse_links(page)
            
            await context.close()
            
            print(f"✅ Found {len(horses)} horses with {name_length} names")
            return horses
            
        except Exception as e:
            print(f"Error filtering: {e}")
            await context.close()
            raise
    
    async def get_all_trainers_horses(self) -> Dict[str, List[Dict]]:
        """Get horses grouped by trainer"""
        print("\n👥 Getting horses by trainer...")
        
        context = await self.browser.new_context()
        page = await context.new_page()
        
        try:
            await page.goto(self.BASE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Find all trainer links
            trainer_links = await page.query_selector_all("a[href*='listbystable?trainerid=']")
            
            trainers_horses = {}
            
            for link in trainer_links:
                href = await link.get_attribute("href")
                trainer_match = re.search(r'trainerid=([^&]+)', href or "")
                
                if not trainer_match:
                    continue
                
                trainer_id = trainer_match.group(1)
                trainer_name = await link.inner_text()
                trainer_name = trainer_name.strip()
                
                print(f"  Processing trainer: {trainer_name} ({trainer_id})")
                
                # Click on trainer to see their horses
                try:
                    await link.click()
                    await asyncio.sleep(2)
                    
                    # Get horses for this trainer
                    horses = await self._extract_horse_links(page)
                    
                    if horses:
                        trainers_horses[trainer_id] = {
                            "trainer_name": trainer_name,
                            "horses": horses
                        }
                        print(f"    Found {len(horses)} horses")
                    
                    # Go back
                    await page.go_back()
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"    Error: {e}")
                    continue
            
            await context.close()
            return trainers_horses
            
        except Exception as e:
            print(f"Error: {e}")
            await context.close()
            raise


async def main():
    """Test scraper"""
    async with HorseListScraper(headless=True) as scraper:
        # Test getting all horses (no filter)
        print("=" * 60)
        print("Test 1: Get all horse IDs")
        print("=" * 60)
        horses = await scraper.get_all_horse_ids()
        
        # Show first 10
        print(f"\nFirst 10 horses:")
        for h in horses[:10]:
            print(f"  {h['horse_id']}: {h['horse_name']}")
        
        print(f"\nTotal: {len(horses)} horses")


if __name__ == "__main__":
    asyncio.run(main())
