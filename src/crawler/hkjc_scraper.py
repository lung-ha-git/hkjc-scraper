"""
HKJC Racing Web Scraper - Enhanced Version
Extracts race results from HKJC website with anti-bot measures
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import re
import time
import random
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HKJCScraper:
    BASE_URL = "https://racing.hkjc.com"
    RESULTS_URL = "/racing/information/English/Racing/LocalResults.aspx"
    
    # List of user agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    
    def __init__(self, delay: Tuple[float, float] = (2, 5)):
        """
        Initialize scraper
        
        Args:
            delay: Random delay range between requests (min, max) seconds
        """
        self.session = requests.Session()
        self.delay_range = delay
        self.last_request_time = 0
        
        logger.info("HKJC Scraper initialized")
    
    def _rotate_user_agent(self):
        """Rotate user agent for each request"""
        user_agent = random.choice(self.USER_AGENTS)
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",  # No gzip
            "DNT": "1",
            "Connection": "keep-alive",
        })
        logger.debug(f"Rotated to user agent: {user_agent[:50]}...")
    
    def _respect_rate_limit(self):
        """Ensure we don't exceed rate limit"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay_range[0]:
            sleep_time = random.uniform(self.delay_range[0], self.delay_range[1]) - elapsed
            if sleep_time > 0:
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
    
    def _make_request(self, url: str, retries: int = 3) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic
        
        Args:
            url: URL to fetch
            retries: Number of retry attempts
            
        Returns:
            Response object or None if all retries fail
        """
        self._respect_rate_limit()
        self._rotate_user_agent()
        
        for attempt in range(retries):
            try:
                logger.info(f"Fetching {url} (attempt {attempt + 1}/{retries})")
                # Disable gzip to avoid decompression issues
                headers = {
                    "Accept-Encoding": "identity",  # Don't accept gzip
                }
                response = self.session.get(url, timeout=30, allow_redirects=True, headers=headers)
                
                if response.status_code == 200:
                    self.last_request_time = time.time()
                    return response
                elif response.status_code == 429:  # Rate limited
                    logger.warning(f"Rate limited (429), backing off...")
                    time.sleep(60)
                else:
                    logger.warning(f"HTTP {response.status_code} for {url}")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"Connection error: {e}")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
            
            if attempt < retries - 1:
                backoff = 2 ** attempt  # Exponential backoff
                logger.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
        
        logger.error(f"Failed to fetch {url} after {retries} attempts")
        return None
    
    def get_race_results(self, date: str) -> List[Dict]:
        """
        Get race results for a specific date
        
        Args:
            date: Format "YYYY-MM-DD"
            
        Returns:
            List of race results
        """
        try:
            # Validate date format
            datetime.strptime(date, "%Y-%m-%d")
            
            date_param = date.replace("-", "")
            url = f"{self.BASE_URL}{self.RESULTS_URL}?RaceDate={date_param}"
            
            response = self._make_request(url)
            if not response:
                return []
            
            return self._parse_results(response.text, date)
            
        except ValueError as e:
            logger.error(f"Invalid date format: {date}. Expected YYYY-MM-DD")
            return []
        except Exception as e:
            logger.error(f"Error getting race results: {e}")
            return []
    
    def _parse_results(self, html: str, date: str) -> List[Dict]:
        """Parse race results from HTML"""
        try:
            soup = BeautifulSoup(html, "lxml")
            races = []
            
            # Find race tables - try multiple selectors
            race_tables = soup.find_all("table", class_=re.compile("race", re.I))
            
            if not race_tables:
                logger.warning(f"No race tables found for {date}")
                # Save HTML for debugging
                self._save_debug_html(html, date)
                return []
            
            logger.info(f"Found {len(race_tables)} race tables")
            
            for idx, table in enumerate(race_tables, 1):
                try:
                    race_data = self._parse_race_table(table, date, idx)
                    if race_data:
                        races.append(race_data)
                        logger.info(f"Parsed race {idx}: {len(race_data.get('runners', []))} runners")
                except Exception as e:
                    logger.error(f"Error parsing race table {idx}: {e}")
                    continue
            
            return races
            
        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            return []
    
    def _parse_race_table(self, table, date: str, race_no: int) -> Optional[Dict]:
        """Parse a single race table"""
        try:
            rows = table.find_all("tr")
            if len(rows) < 2:  # Need at least header + 1 data row
                return None
            
            runners = []
            for row in rows[1:]:  # Skip header
                try:
                    cols = row.find_all("td")
                    if len(cols) >= 6:
                        runner = {
                            "position": cols[0].get_text(strip=True),
                            "horse_no": cols[1].get_text(strip=True),
                            "horse_name": cols[2].get_text(strip=True),
                            "jockey": cols[3].get_text(strip=True),
                            "trainer": cols[4].get_text(strip=True),
                            "finish_time": cols[5].get_text(strip=True),
                            "margin": cols[6].get_text(strip=True) if len(cols) > 6 else ""
                        }
                        runners.append(runner)
                except Exception as e:
                    logger.debug(f"Error parsing runner row: {e}")
                    continue
            
            if not runners:
                return None
            
            return {
                "race_id": f"{date.replace('-','')}_R{race_no}",
                "date": date,
                "race_no": race_no,
                "venue": self._detect_venue(html=str(table)),
                "runners": runners,
                "scraped_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in _parse_race_table: {e}")
            return None
    
    def _detect_venue(self, html: str) -> str:
        """Detect venue from HTML content"""
        if "Happy Valley" in html or "快活谷" in html:
            return "HV"
        elif "Sha Tin" in html or "沙田" in html:
            return "ST"
        return "Unknown"
    
    def _save_debug_html(self, html: str, date: str):
        """Save HTML for debugging purposes"""
        try:
            debug_dir = Path("logs/debug")
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            filename = debug_dir / f"{date}_debug.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)
            
            logger.info(f"Saved debug HTML to {filename}")
        except Exception as e:
            logger.error(f"Failed to save debug HTML: {e}")
    
    def get_recent_results(self, days: int = 7) -> List[Dict]:
        """Get results for recent days"""
        results = []
        today = datetime.now()
        
        logger.info(f"Fetching results for last {days} days...")
        
        for i in range(days):
            date = today - timedelta(days=i)
            # Skip Wednesdays and Sundays (typical race days)
            if date.weekday() in [2, 6]:  # Wednesday=2, Sunday=6
                date_str = date.strftime("%Y-%m-%d")
                day_results = self.get_race_results(date_str)
                results.extend(day_results)
                
                # Random delay between days
                if i < days - 1:
                    time.sleep(random.uniform(3, 6))
        
        logger.info(f"Total races fetched: {len(results)}")
        return results


if __name__ == "__main__":
    # Test with logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    scraper = HKJCScraper(delay=(3, 6))
    
    # Test with a specific date
    test_date = "2026-03-01"
    results = scraper.get_race_results(test_date)
    
    logger.info(f"Found {len(results)} races on {test_date}")
    for race in results[:2]:  # Show first 2 races
        logger.info(f"  Race {race['race_no']}: {len(race['runners'])} runners")
