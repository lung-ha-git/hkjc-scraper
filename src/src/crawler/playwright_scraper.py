"""
HKJC Playwright Scraper - Enhanced Version
Uses Playwright for JavaScript-rendered pages
"""

import asyncio
from playwright.async_api import async_playwright, Page
from datetime import datetime
from typing import List, Dict, Optional
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HKJCPlaywrightScraper:
    """Scraper using Playwright for JavaScript-rendered pages"""
    
    def __init__(self, headless: bool = True, delay: int = 3):
        self.headless = headless
        self.delay = delay
        self.browser = None
        self.context = None
        
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
    
    async def scrape_jockey_ranking(self) -> List[Dict]:
        """
        Scrape jockey rankings
        URL: https://racing.hkjc.com/zh-hk/local/info/jockey-ranking
        """
        url = "https://racing.hkjc.com/zh-hk/local/info/jockey-ranking?season=Current&view=Numbers&racecourse=ALL"
        
        page = await self.context.new_page()
        
        try:
            logger.info(f"Navigating to jockey rankings")
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(self.delay * 1000)
            
            jockeys = await self._extract_jockeys_from_page(page)
            logger.info(f"Found {len(jockeys)} jockeys")
            return jockeys
            
        except Exception as e:
            logger.error(f"Error scraping jockeys: {e}")
            return []
        finally:
            await page.close()
    
    async def scrape_trainer_ranking(self) -> List[Dict]:
        """
        Scrape trainer rankings
        URL: https://racing.hkjc.com/zh-hk/local/info/trainer-ranking
        """
        url = "https://racing.hkjc.com/zh-hk/local/info/trainer-ranking?season=Current&view=Numbers&racecourse=ALL"
        
        page = await self.context.new_page()
        
        try:
            logger.info(f"Navigating to trainer rankings")
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_timeout(self.delay * 1000)
            
            trainers = await self._extract_trainers_from_page(page)
            logger.info(f"Found {len(trainers)} trainers")
            return trainers
            
        except Exception as e:
            logger.error(f"Error scraping trainers: {e}")
            return []
        finally:
            await page.close()
    
    async def _extract_jockeys_from_page(self, page: Page) -> List[Dict]:
        """Extract jockey rankings from page"""
        jockeys = []
        try:
            tables = await page.query_selector_all("table")
            
            # Use the second table which contains the data
            if len(tables) < 2:
                logger.warning("Not enough tables found")
                return jockeys
            
            data_table = tables[1]  # Second table has the ranking data
            rows = await data_table.query_selector_all("tr")
            
            logger.info(f"Found {len(rows)} rows in jockey table")
            
            rank = 1
            for row in rows[1:]:  # Skip header
                cells = await row.query_selector_all("td")
                if len(cells) >= 5:
                    try:
                        name = await cells[0].inner_text()
                        wins = await cells[1].inner_text()
                        second = await cells[2].inner_text()
                        third = await cells[3].inner_text()
                        fourth = await cells[4].inner_text()
                        
                        name_clean = name.strip()
                        
                        # Skip header row
                        if name_clean == '騎師' or '騎師榜' in name_clean:
                            continue
                        
                        jockey = {
                            "jockey_id": f"jockey_{name_clean}",
                            "name": name_clean,
                            "rank": rank,
                            "wins": wins.strip(),
                            "second": second.strip(),
                            "third": third.strip(),
                            "fourth": fourth.strip(),
                            "scraped_at": datetime.now().isoformat()
                        }
                        jockeys.append(jockey)
                        rank += 1
                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error extracting jockeys: {e}")
        return jockeys
    
    async def _extract_trainers_from_page(self, page: Page) -> List[Dict]:
        """Extract trainer rankings from page"""
        trainers = []
        try:
            tables = await page.query_selector_all("table")
            
            if len(tables) < 2:
                return trainers
            
            data_table = tables[1]
            rows = await data_table.query_selector_all("tr")
            
            rank = 1
            for row in rows[1:]:
                cells = await row.query_selector_all("td")
                if len(cells) >= 5:
                    try:
                        name = await cells[0].inner_text()
                        wins = await cells[1].inner_text()
                        second = await cells[2].inner_text()
                        third = await cells[3].inner_text()
                        fourth = await cells[4].inner_text()
                        
                        name_clean = name.strip()
                        
                        if name_clean == '練馬師' or '練馬師榜' in name_clean:
                            continue
                        
                        trainer = {
                            "trainer_id": f"trainer_{name_clean}",
                            "name": name_clean,
                            "rank": rank,
                            "wins": wins.strip(),
                            "second": second.strip(),
                            "third": third.strip(),
                            "fourth": fourth.strip(),
                            "scraped_at": datetime.now().isoformat()
                        }
                        trainers.append(trainer)
                        rank += 1
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error extracting trainers: {e}")
        return trainers


# Synchronous wrapper
def scrape_jockeys_sync() -> List[Dict]:
    """Synchronous wrapper for jockey scraping"""
    async def _scrape():
        async with HKJCPlaywrightScraper() as scraper:
            return await scraper.scrape_jockey_ranking()
    
    return asyncio.run(_scrape())


def scrape_trainers_sync() -> List[Dict]:
    """Synchronous wrapper for trainer scraping"""
    async def _scrape():
        async with HKJCPlaywrightScraper() as scraper:
            return await scraper.scrape_trainer_ranking()
    
    return asyncio.run(_scrape())


if __name__ == "__main__":
    # Test
    async def test():
        async with HKJCPlaywrightScraper(headless=True) as scraper:
            jockeys = await scraper.scrape_jockey_ranking()
            print(f"Scraped {len(jockeys)} jockeys")
            for j in jockeys[:5]:
                print(f"  {j['rank']}. {j['name']}: {j['wins']} wins")
    
    asyncio.run(test())
