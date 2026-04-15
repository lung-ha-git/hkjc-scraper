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

        # Intercept raceMeetings GraphQL request and inject correct date/venue variables.
        # The page JS may send a stale date; we abort that request and re-send with the
        # user-supplied (race_date, venue) parameters so the API returns the right meeting.
        async def handle_route(route):
            req = route.request
            if req.method != "POST" or "graphql" not in req.url:
                await route.continue_()
                return

            body = req.post_data or ""
            try:
                parsed = json.loads(body)
                if parsed.get("operationName") != "raceMeetings":
                    await route.continue_()
                    return
            except Exception:
                await route.continue_()
                return

            logger.info(f"   Intercepted raceMeetings request — expected date={race_date}, venue={venue}")
            # Abort the original (possibly stale) request
            await route.abort()

            # Re-send with correct variables via page context
            graphql_query = """
            query raceMeetings($date: String!, $venueCode: String!) {
                raceMeetings(date: $date, venueCode: $venueCode) {
                    id
                    date
                    name { zh_TW en_US }
                    venue { code displayName }
                    races {
                        no
                        distance
                        postTime
                        raceName_en
                        raceName_ch
                        ratingType
                        raceTrack { description_en description_ch }
                        raceCourse { displayCode }
                        raceClass_en
                        raceClass_ch
                        runners {
                            no
                            name_ch
                            name_en
                            status
                            finalPosition
                            trumpCard
                            priority
                            handicapWeight
                            currentRating
                            last6run
                            gearInfo
                            color
                            horse { code id }
                            jockey { code name_ch name_en }
                            trainer { code name_ch name_en }
                            barrierDrawNumber: barrierDraw
                        }
                    }
                }
            }"""
            await page.evaluate(
                """async (url, query, variables) => {
                    await fetch(url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ operationName: 'raceMeetings', variables, query })
                    });
                }""",
                self.GRAPHQL_URL,
                graphql_query,
                {"date": race_date, "venueCode": venue}
            )
            logger.info(f"   Re-sent raceMeetings request with date={race_date}, venueCode={venue}")

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

                    # postTime 是真正的比賽日（用 input race_date 不可靠，
                    # 因為 World Pool / 補抓時 input date ≠ actual race date）
                    actual_post_time = race.get("postTime", "")
                    actual_race_date = actual_post_time[:10]  # "2026-04-04"

                    race_meta = {
                        "race_no": race_no,
                        "race_date": actual_race_date,
                        "venue": venue,
                        "distance": dist,
                        "race_name_en": race.get("raceName_en", ""),
                        "race_name_ch": race.get("raceName_ch", ""),
                        "post_time": actual_post_time,
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

        # Ensure every card has a race_id (needed for upsert by callers)
        for rc in racecards:
            if "race_id" not in rc:
                rc["race_id"] = f"{rc.get('race_date', '').replace('-', '_')}_{rc.get('venue', '')}_{rc.get('race_no', '')}"

        logger.info(f"   ✅ Scraped {len(racecards)} races")
        return racecards

    # World Pool race name keywords (case-insensitive)
    # ⚠️ 只用精確匹配的關鍵字，避免誤殺同名本地賽
    # 例如 "Chairman's Trophy" 是本地賽，不能用 "chairman"
    _WP_KEYWORDS = [
        # Explicit World Pool branding
        "world pool", "worldpool",
        "全球匯合彩池", "全球彩池",
        # Country-specific keywords in race name
        "australia", "(aus)", "(nz)", "(uk)", "(ire)",
        "澳洲", "紐西蘭", "英國", "愛爾蘭",
        # World Pool specific race names (精確匹配)
        "co trophy", "co. trophy",
        # 2026-04-08 World Pool races
        "chairman's quality",  # 主席讓賽 (World Pool)
        "doncaster",           # 唐加士打一哩賽 (World Pool)
        "baaqar",              # Baaqar Stakes (World Pool)
        # 2026-04-11 World Pool races
        "香港賽馬會全球匯合彩池",  # 精確中文名
        "悉尼盃",          # Sydney Cup (Australia)
        "藍寶石",          # Sapphire Stakes (Australia)
        "南太平洋",        # South Pacific Classic (Australia)
        "珀斯",            # Perth races (Percy Sykes, etc)
        "皇治",            # Royal Sovereign Stakes (Australia)
        "決賽",            # Championships Finals (Australia)
        # 2026-04-04 World Pool races
        "葉健士公開賽",  # The Quokka Cup (Perth, World Pool)
        "澳洲盃",        # 澳洲盃 (World Pool)
        # 2026-04-08 Australian WP races
        "鄉郊",          # Country Championships (Australia)
        "育馬",          # Sires' Produce (Australia)
        "史密夫",        # T J Smith Stakes (Australia)
        "貝堯",          # P J Bell Stakes (Australia)
    ]

    def _detect_race_type(self, race_name_en: str, race_name_ch: str) -> str:
        """
        Detect whether a race is a World Pool (overseas/international) race.
        Uses race name keywords as the primary signal.
        Returns 'world_pool' or 'local'.
        """
        combined = f"{race_name_en} {race_name_ch}".lower()
        for kw in self._WP_KEYWORDS:
            if kw.lower() in combined:
                return "world_pool"
        return "local"

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
                # Detect race_type from race name keywords
                race_type = self._detect_race_type(
                    rc.get("race_name_en", ""),
                    rc.get("race_name_ch", "")
                )
                doc = {
                    **rc,
                    "race_id": race_id,
                    "race_type": race_type,
                    "scrape_at": datetime.now(),
                }
                # Upsert each race
                collection.update_one(
                    {"race_id": race_id}, {"$set": doc}, upsert=True
                )
                if race_type == "world_pool":
                    logger.info(f"   🌍 World Pool detected: R{rc['race_no']} — {rc.get('race_name_ch', '')}")
                count += 1
            logger.info(f"   💾 Saved {count} races to MongoDB (race_type set)")
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
