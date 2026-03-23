"""
HKJC Race Card Scraper — GraphQL version (replaces HTML scraping)

Source: bet.hkjc.com GraphQL raceMeetings operation
Replaces: HTML parsing of racing.hkjc.com racecard pages

URL pattern: https://bet.hkjc.com/ch/racing/wp/{date}/{venue}/{raceNo}
GraphQL: POST info.cld.hkjc.com/graphql/base/
Operation: raceMeetings (variables: date, venueCode)
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List

from playwright.async_api import async_playwright
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import get_db

logger = logging.getLogger(__name__)


class RaceCardScraper:
    """Scrape HKJC race cards via GraphQL — single request per meeting"""

    GRAPHQL_URL = "https://info.cld.hkjc.com/graphql/base/"
    BET_URL_TPL = "https://bet.hkjc.com/ch/racing/wp/{date}/{venue}/1"

    def __init__(self, headless: bool = True, delay: int = 2):
        self.headless = headless
        self.delay = delay
        self.browser = None
        self.playwright = None
        self._racecards = []

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            channel="chrome" if not self.headless else None
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    def _jersey_url(self, horse_id: str) -> str:
        """Generate jersey image URL from horse code"""
        if not horse_id:
            return ""
        return f"https://racing.hkjc.com/racing/content/Images/RaceColor/{horse_id}.gif"

    async def scrape_race_day(
        self, race_date: str, venue: str = "HV", max_races: int = 12
    ) -> List[Dict]:
        """
        Scrape all race cards for a given day via GraphQL.

        NOTE: The GraphQL raceMeetings operation returns the NEXT scheduled meeting,
        not a historical one. The date/venue parameters filter to the nearest meeting.
        For past-race queries (e.g. after results are out), use the HTML scraper or
        accept that this will return the next upcoming meeting.

        Args:
            race_date: Format YYYY-MM-DD (informational — may return next meeting)
            venue: HV or ST

        Returns:
            List of race card dicts, each with race metadata + 'horses' list.
        """
        logger.info(f"🏇 GraphQL: scraping {race_date} ({venue})...")

        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        self._racecards = []
        racecards = self._racecards

        # Intercept raceMeetings GraphQL responses only
        # NOTE: route handler is sync in Python Playwright
        def handle_route(route):
            """Sync route handler — check op, intercept response."""
            req = route.request
            if req.method != "POST" or "graphql" not in req.url:
                route.continue_()
                return

            body = req.post_data or ""
            try:
                parsed = json.loads(body)
                if parsed.get("operationName") != "raceMeetings":
                    route.continue_()
                    return
            except Exception:
                route.continue_()
                return

            # Intercept: continue to get the real response, then fulfill modified
            route.continue_()

        # Response handler to parse raceMeetings data
        async def handle_response(response):
            url = response.url
            if "graphql" not in url or response.status != 200:
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                text = await response.text()
                if len(text) < 1000:
                    return

                json_data = json.loads(text)
                meetings = json_data.get("data", {}).get("raceMeetings", [])
                if not meetings:
                    return

                meeting = meetings[0]
                races = meeting.get("races", [])
                logger.info(
                    f"   GraphQL: got {len(races)} races from meeting {meeting.get('id', '?')}"
                )

                for race in races:
                    race_no = int(race.get("no", 0))
                    if race_no == 0 or race_no > max_races:
                        continue
                    dist = race.get("distance") or 0
                    if dist == 0:
                        continue

                    race_meta = {
                        "race_no": race_no,
                        "race_date": race_date,
                        "venue": venue,
                        "distance": dist,
                        "race_name_en": race.get("raceName_en", ""),
                        "race_name_ch": race.get("raceName_ch", ""),
                        "post_time": race.get("postTime", ""),
                        "rating_type": race.get("ratingType", ""),
                        "race_track": (
                            race.get("raceTrack", {}).get("description_en", "")
                            or race.get("raceTrack", {}).get("description_ch", "")
                        ),
                        "race_course": race.get("raceCourse", {}).get("displayCode", ""),
                        "class_en": race.get("raceClass_en", ""),
                        "class_ch": race.get("raceClass_ch", ""),
                    }

                    horses = []
                    for horse in race.get("runners", []):
                        horse_id = horse.get("horse", {}).get("code", "") or ""
                        hkjc_id = horse.get("horse", {}).get("id", "") or ""
                        entry = {
                            "horse_no": int(horse.get("no") or 0),
                            "horse_name": horse.get("name_ch") or horse.get("name_en", ""),
                            "jockey_name": (
                                horse.get("jockey", {}).get("name_ch")
                                or horse.get("jockey", {}).get("name_en", "")
                            ),
                            "jockey_code": horse.get("jockey", {}).get("code", ""),
                            "trainer_name": (
                                horse.get("trainer", {}).get("name_ch")
                                or horse.get("trainer", {}).get("name_en", "")
                            ),
                            "trainer_code": horse.get("trainer", {}).get("code", ""),
                            "draw": horse.get("barrierDrawNumber"),
                            "weight_carried": horse.get("handicapWeight"),
                            "rating": horse.get("currentRating"),
                            "equipment": horse.get("gearInfo", "-"),
                            "recent_form": horse.get("last6run", ""),
                            "jersey_url": self._jersey_url(horse_id),
                            "horse_id": horse_id,
                            "hkjc_horse_id": hkjc_id,
                            "horse_color": horse.get("color", ""),
                            "status": horse.get("status", "Declared"),
                            "final_position": horse.get("finalPosition"),
                            "trump_card": bool(horse.get("trumpCard")),
                            "priority": bool(horse.get("priority")),
                            # legacy / compatibility fields
                            "scratch_weight": 1,
                            "rating_change": None,
                        }
                        horses.append(entry)

                    race_meta["horses"] = horses
                    racecards.append(race_meta)
                    logger.info(
                        f"   ✅ R{race_no}: {len(horses)} horses "
                        f"{dist}m {race_meta.get('class_ch', '')}"
                    )
            except Exception as e:
                logger.error(f"   Response parse error: {e}")

        page.on("response", handle_response)
        page.on("route", handle_route)

        await page.goto(
            self.BET_URL_TPL.format(date=race_date, venue=venue),
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await page.wait_for_timeout(4000)
        await context.close()

        racecards.sort(key=lambda r: r["race_no"])
        logger.info(f"   ✅ Scraped {len(racecards)} races")
        return racecards

    def save_to_mongodb(self, racecards: List[Dict]) -> bool:
        """Save race cards to MongoDB. Matches original interface."""
        if not racecards:
            return False
        try:
            db = get_db()
            collection = db.get_collection("racecards")
            count = 0
            for rc in racecards:
                race_id = (
                    f"{rc['race_date'].replace('-', '_')}_{rc['venue']}_{rc['race_no']}"
                )
                doc = {**rc, "race_id": race_id, "scrape_at": datetime.now()}
                # Upsert each race
                collection.update_one(
                    {"race_id": race_id}, {"$set": doc}, upsert=True
                )
                count += 1
            logger.info(f"   💾 Saved {count} races to MongoDB")
            return True
        except Exception as e:
            logger.error(f"   ❌ MongoDB save failed: {e}")
            return False


async def main():
    """Test standalone"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with RaceCardScraper(headless=True) as scraper:
        racecards = await scraper.scrape_race_day("2026-03-22", "ST")
        print(f"\nResult: {len(racecards)} races")
        if racecards:
            print(f"  R1: {len(racecards[0]['horses'])} horses")


if __name__ == "__main__":
    asyncio.run(main())
