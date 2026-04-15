"""
HKJC Fixture Scraper
Download race meeting calendar to MongoDB
"""

import asyncio
import re
from playwright.async_api import async_playwright
from typing import List, Dict, Optional
from datetime import datetime
import sys
from pathlib import Path
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

# Months to fetch (full season: Sep - Jul)
MONTHS = [
    ("2025", "09"), ("2025", "10"), ("2025", "11"), ("2025", "12"),
    ("2026", "01"), ("2026", "02"), ("2026", "03"), ("2026", "04"),
    ("2026", "05"), ("2026", "06"), ("2026", "07")
]

FIXTURE_URL = "https://racing.hkjc.com/zh-hk/local/information/fixture"


class FixtureScraper:
    """Scrape HKJC race fixture/calendar"""

    def __init__(self, headless: bool = True):
        self.headless = headless

    async def _probe_venue_from_racecards(self, date_str: str) -> tuple[Optional[str], int]:
        """
        Probe both HV and ST racecard pages in parallel and return the venue
        that has actual race data.

        This replaces the old HTML keyword ('田'/'谷') venue detection, which
        was unreliable for dates like 2026-04-15.

        Returns: (venue_code, race_count) — venue is None if neither has races.
        """
        date_fmt = date_str.replace("-", "/")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            async def check_venue(venue: str) -> tuple[str, int]:
                page = await browser.new_page()
                url = (f"https://racing.hkjc.com/en-us/local/information/racecard"
                       f"?racedate={date_fmt}&Racecourse={venue}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(1.5)
                    content = await page.inner_text("body")

                    if "沒有相關資料" in content or len(content) < 800:
                        return (venue, 0)

                    links = await page.query_selector_all("a[href*='RaceNo=']")
                    race_nos = []
                    for link in links:
                        href = await link.get_attribute("href")
                        m = re.search(r'RaceNo=(\d+)', href or "")
                        if m:
                            race_nos.append(int(m.group(1)))

                    return (venue, max(race_nos) if race_nos else 0)
                except Exception as e:
                    logger.debug(f"Racecard probe failed for {date_str} ({venue}): {e}")
                    return (venue, 0)
                finally:
                    await page.close()

            hv_races, st_races = await asyncio.gather(
                check_venue("HV"), check_venue("ST")
            )
            await browser.close()

        hv_count = hv_races[1]
        st_count = st_races[1]

        if hv_count > 0 and st_count == 0:
            return ("HV", hv_count)
        elif st_count > 0 and hv_count == 0:
            return ("ST", st_count)
        elif hv_count > st_count:
            return ("HV", hv_count)
        elif st_count > hv_count:
            return ("ST", st_count)
        else:
            # Neither has published racecards yet (future date).
            # Return None and let the caller decide (HTML keyword fallback).
            return (None, 0)

    async def _resolve_venue_from_html_keywords(self, cell_text: str) -> str:
        """Fallback: detect venue from fixture HTML cell text keywords."""
        return 'HV' if '谷' in cell_text else 'ST'

    async def parse_month(self, year: str, month: str) -> List[Dict]:
        """Parse fixture for a specific month."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()

            url = f"{FIXTURE_URL}?calyear={year}&calm={month}"
            logger.info(f"Fetching: {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                table = await page.query_selector("table.table_bd")
                if not table:
                    logger.warning(f"No table found for {year}-{month}")
                    await browser.close()
                    return []

                rows = await table.query_selector_all("tr")
                race_meetings = []
                current_month = int(month)

                for row in rows:
                    cells = await row.query_selector_all("td")

                    for cell in cells:
                        text = await cell.inner_text()

                        if '星期' in text:
                            continue

                        race_nums = re.findall(r'\((\d+)\)', text)
                        if race_nums:
                            date_match = re.search(r'^(\d{1,2})', text.strip())
                            if date_match and current_month:
                                day = int(date_match.group(1))
                                date_str = f"{year}-{current_month:02d}-{day:02d}"

                                # Probe HV and ST racecard pages to find the real venue
                                venue, race_count = await self._probe_venue_from_racecards(date_str)

                                if venue is None:
                                    # No published racecards yet — fall back to HTML keyword
                                    venue = await self._resolve_venue_from_html_keywords(text)
                                    race_count = max(int(r) for r in race_nums)
                                    logger.info(
                                        f"  {date_str}: racecards unpublished, "
                                        f"keyword fallback → {venue} ({race_count} races)"
                                    )
                                else:
                                    logger.info(
                                        f"  {date_str} ({venue}): {race_count} races (confirmed via racecard probe)"
                                    )

                                race_meetings.append({
                                    'date': date_str,
                                    'venue': venue,
                                    'race_count': race_count,
                                    'source_url': FIXTURE_URL,
                                    'racecard_url': (
                                        f"https://racing.hkjc.com/zh-hk/local/information/racecard"
                                        f"?racedate={year}/{month}/{day:02d}&Racecourse={venue}"
                                    ),
                                    'results_url': (
                                        f"https://racing.hkjc.com/zh-hk/racing/information/"
                                        f"English/Racing/LocalResults.aspx?RaceDate={date_str}"
                                    ),
                                    'scrape_status': 'pending',
                                    'created_at': datetime.now(),
                                    'modified_at': datetime.now()
                                })

            except Exception as e:
                logger.error(f"Error fetching {year}-{month}: {e}")
            finally:
                await browser.close()

            return race_meetings

    async def scrape_all(self) -> List[Dict]:
        """Scrape all months."""
        all_meetings = []

        for year, month in MONTHS:
            logger.info(f"Processing {year}-{month}...")
            meetings = await self.parse_month(year, month)
            logger.info(f"  Found {len(meetings)} meetings")
            all_meetings.extend(meetings)

        return all_meetings

    def save_to_mongodb(self, meetings: List[Dict]) -> bool:
        """Save fixtures to MongoDB."""
        logger.info(f"Saving {len(meetings)} fixtures to MongoDB...")

        db = DatabaseConnection()
        if not db.connect():
            logger.error("Cannot connect to MongoDB")
            return False

        db.db["fixtures"].delete_many({})
        if meetings:
            db.db["fixtures"].insert_many(meetings)

        count = db.db["fixtures"].count_documents({})
        logger.info(f"Fixtures in DB: {count}")

        db.disconnect()
        return True


async def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scraper = FixtureScraper(headless=True)
    meetings = await scraper.scrape_all()
    scraper.save_to_mongodb(meetings)

    print("\n" + "=" * 60)
    print("📊 FIXTURE SCRAPER COMPLETE")
    print("=" * 60)
    print(f"Total meetings: {len(meetings)}")


if __name__ == "__main__":
    asyncio.run(main())
