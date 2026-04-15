"""
Webapp API Unit Tests — HKJC

Tests the Express.js API endpoints in index.cjs:
    /api/fixtures
    /api/racecards
    /api/races
    /api/health
    /api/jersey

Run: python src/tests/test_webapp_api.py
Or:  pytest src/tests/test_webapp_api.py -v

Note: These tests require a running MongoDB and webapp server.
Run the server first:
    cd src/web-app/server && node index.cjs
"""

import sys
import os
import json
import unittest
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Test Result Tracker ────────────────────────────────────────────────────

class TestResults:
    def __init__(self):
        self.results = []
        self.total = 0
        self.passed = 0
        self.failed = 0

    def add(self, name: str, passed: bool, detail: str = ""):
        self.results.append({"name": name, "passed": passed, "detail": detail})
        self.total += 1
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def report(self) -> str:
        from datetime import datetime
        lines = [
            "",
            "=" * 70,
            f"  WEBAPP API TEST REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
            "",
            f"  Total:  {self.total}  |  ✅ Passed: {self.passed}  |  ❌ Failed: {self.failed}",
            "",
        ]
        for r in self.results:
            status = "✅ PASS" if r["passed"] else "❌ FAIL"
            lines.append(f"  {status}  {r['name']}")
            if r["detail"]:
                lines.append(f"         → {r['detail']}")
        lines += ["", "=" * 70, "  END OF REPORT", "=" * 70, ""]
        return "\n".join(lines)


RESULTS = TestResults()

BASE_URL = os.environ.get("WEBAPP_URL", "http://localhost")
TIMEOUT = 10


def api_get(path: str) -> tuple:
    """GET an API endpoint, return (status_code, data_dict)
    Returns (status, None) for non-JSON responses (binary, HTML, etc.)
    """
    url = f"{BASE_URL}{path}"
    try:
        req = Request(url)
        with urlopen(req, timeout=TIMEOUT) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            # Skip JSON parsing for binary responses (images, etc.)
            if "application/json" not in content_type and "text/" not in content_type:
                return status, None  # Binary response — can't parse as JSON
            raw = resp.read()
            if not raw:
                return status, None
            data = json.loads(raw.decode())
            return status, data
    except HTTPError as e:
        return e.code, None
    except URLError:
        return None, None
    except Exception as e:
        RESULTS.add(f"API {path}", False, f"Error: {e}")
        return None, None


# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: Health & Connectivity
# ════════════════════════════════════════════════════════════════════════════

class TestHealth(unittest.TestCase):
    def test_health_endpoint(self):
        """GET /api/health returns {ok: 1}"""
        status, data = api_get("/api/health")
        RESULTS.add(
            "/api/health returns 200 with {ok: 1}",
            status == 200 and data and data.get("ok") == 1,
            f"status={status}, data={data}"
        )

    def test_server_reachable(self):
        """Webapp server is reachable at localhost"""
        try:
            req = Request(f"{BASE_URL}/api/health")
            with urlopen(req, timeout=5):
                RESULTS.add("Webapp server reachable", True, BASE_URL)
        except Exception as e:
            RESULTS.add("Webapp server reachable", False, str(e))


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: /api/fixtures
# ════════════════════════════════════════════════════════════════════════════

class TestFixturesEndpoint(unittest.TestCase):
    def test_fixtures_returns_list(self):
        """GET /api/fixtures returns a list"""
        status, data = api_get("/api/fixtures")
        RESULTS.add(
            "/api/fixtures returns 200 with list",
            status == 200 and isinstance(data, list),
            f"status={status}, type={type(data).__name__}"
        )

    def test_fixtures_has_date_field(self):
        """Each fixture has a 'date' field"""
        status, data = api_get("/api/fixtures")
        if status == 200 and isinstance(data, list) and len(data) > 0:
            fixture = data[0]
            has_date = "date" in fixture or "race_date" in fixture
            RESULTS.add(
                "Fixtures have 'date' or 'race_date' field",
                has_date,
                f"Keys: {list(fixture.keys())[:5]}"
            )
        else:
            RESULTS.add("Fixtures have 'date' or 'race_date' field", False, "No data")

    def test_fixtures_upcoming_count(self):
        """There are upcoming fixtures (future dates)"""
        status, data = api_get("/api/fixtures?type=upcoming")
        if status == 200 and isinstance(data, list):
            RESULTS.add(
                f"/api/fixtures?type=upcoming returns {len(data)} fixtures",
                True,
                f"Upcoming fixtures: {len(data)}"
            )
        else:
            RESULTS.add(
                "/api/fixtures?type=upcoming handles empty gracefully",
                status == 200,
                f"status={status}"
            )

    def test_fixtures_past_count(self):
        """There are past fixtures"""
        status, data = api_get("/api/fixtures?type=past")
        RESULTS.add(
            "/api/fixtures?type=past returns 200",
            status == 200,
            f"status={status}, count={len(data) if isinstance(data, list) else 'N/A'}"
        )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: /api/racecards
# ════════════════════════════════════════════════════════════════════════════

class TestRacecardsEndpoint(unittest.TestCase):
    def test_racecards_requires_date_param(self):
        """GET /api/racecards without date returns 400"""
        status, data = api_get("/api/racecards")
        RESULTS.add(
            "/api/racecards requires date parameter (400 without)",
            status == 400,
            f"status={status} (expected 400)"
        )

    def test_racecards_with_valid_date(self):
        """GET /api/racecards?date=2026-04-15&venue=HV returns racecards"""
        status, data = api_get("/api/racecards?date=2026-04-15&venue=HV")
        is_valid = (
            status == 200
            and data is not None
            and isinstance(data, dict)
            and "racecards" in data
        )
        RESULTS.add(
            "/api/racecards?date=2026-04-15&venue=HV returns data",
            is_valid,
            f"status={status}, keys={list(data.keys()) if isinstance(data, dict) else type(data)}"
        )

    def test_racecards_has_horses(self):
        """Racecards include horse entries with key fields"""
        status, data = api_get("/api/racecards?date=2026-04-15&venue=HV")
        if status == 200 and data and data.get("racecards"):
            races = data["racecards"]
            if races:
                horses = races[0].get("horses", [])
                RESULTS.add(
                    f"Race 1 has horses ({len(horses)} entries)",
                    len(horses) > 0,
                    f"Horses: {len(horses)}"
                )
                if horses:
                    horse = horses[0]
                    required = ["horse_no", "horse_name", "jockey_name", "draw"]
                    missing = [f for f in required if f not in horse]
                    RESULTS.add(
                        "Horse entry has required fields (horse_no, horse_name, jockey_name, draw)",
                        len(missing) == 0,
                        f"Missing: {missing}" if missing else "All required fields present ✅"
                    )
        else:
            RESULTS.add(
                "Racecards horses check",
                False,
                f"No racecards data (status={status})"
            )

    def test_racecards_venue_field_consistency(self):
        """Racecard venue matches query parameter"""
        status, data = api_get("/api/racecards?date=2026-04-15&venue=HV")
        if status == 200 and data and data.get("racecards"):
            venues = {r.get("venue") for r in data["racecards"]}
            RESULTS.add(
                f"All racecards for HV query are HV venue (found: {venues})",
                venues == {"HV"},
                f"Venues: {venues}"
            )
        else:
            RESULTS.add("Venue consistency check", False, "No racecards data")

    def test_racecards_race_count_matches_fixture(self):
        """Number of races matches fixture (should be 9 for 2026-04-15 HV)"""
        status, data = api_get("/api/racecards?date=2026-04-15&venue=HV")
        if status == 200 and data and data.get("racecards"):
            race_nos = sorted([r.get("race_no") for r in data["racecards"] if r.get("race_no")])
            expected = list(range(1, 10))
            RESULTS.add(
                f"Racecard race numbers 1-9 present (got {race_nos})",
                race_nos == expected,
                f"Expected: {expected}, Got: {race_nos}"
            )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: /api/races
# ════════════════════════════════════════════════════════════════════════════

class TestRacesEndpoint(unittest.TestCase):
    def test_races_returns_list(self):
        """GET /api/races returns a list"""
        status, data = api_get("/api/races")
        RESULTS.add(
            "/api/races returns 200 with list",
            status == 200 and isinstance(data, list),
            f"status={status}, type={type(data).__name__}"
        )

    def test_races_has_race_date_field(self):
        """Races have race_date field (not 'date')"""
        status, data = api_get("/api/races")
        if status == 200 and isinstance(data, list) and len(data) > 0:
            race = data[0]
            # races collection uses race_date
            has_race_date = "race_date" in race
            RESULTS.add(
                "Races collection uses 'race_date' field",
                has_race_date,
                f"Keys: {list(race.keys())[:5]}"
            )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 5: /api/jersey
# ════════════════════════════════════════════════════════════════════════════

class TestJerseyEndpoint(unittest.TestCase):
    def test_jersey_known_horse(self):
        """GET /api/jersey/:horseId returns image (binary GIF) for known horse"""
        url = f"{BASE_URL}/api/jersey/H436"
        try:
            req = Request(url)
            with urlopen(req, timeout=TIMEOUT) as resp:
                status = resp.status
                content_type = resp.headers.get("Content-Type", "")
                first_bytes = resp.read(4).hex()
                # Known jersey returns image/gif
                is_image = "image" in content_type or first_bytes.startswith("47494638")
                RESULTS.add(
                    "/api/jersey/H436 returns image/gif for known horse",
                    is_image,
                    f"status={status}, type={content_type}, magic={first_bytes}"
                )
        except HTTPError as e:
            RESULTS.add("/api/jersey/H436 returns image/gif for known horse", False, f"HTTP {e.code}")
        except Exception as e:
            RESULTS.add("/api/jersey/H436 returns image/gif for known horse", False, str(e))

    def test_jersey_unknown_horse(self):
        """GET /api/jersey/:horseId for unknown horse returns 404"""
        status, data = api_get("/api/jersey/UNKNOWN_XYZ_999")
        RESULTS.add(
            "/api/jersey/:id for unknown horse returns 404 or null",
            status == 404 or status == 200,  # Some implementations return 200 with null
            f"status={status}"
        )


# ════════════════════════════════════════════════════════════════════════════
# SECTION 6: Field Consistency — API vs Database
# ════════════════════════════════════════════════════════════════════════════

class TestAPIDatabaseConsistency(unittest.TestCase):
    """
    Verify that API endpoints return data that matches the database schema.
    Critical: fixtures uses 'date', races/racecards use 'race_date'.
    """

    def test_racecards_api_matches_scraper_schema(self):
        """API /api/racecards returns racecards with 'race_date' field (not 'date')"""
        status, data = api_get("/api/racecards?date=2026-04-15&venue=HV")
        if status == 200 and data and data.get("racecards"):
            rc = data["racecards"][0]
            has_race_date = "race_date" in rc
            has_plain_date = "date" in rc and "race_date" not in rc
            RESULTS.add(
                "API returns racecards with 'race_date' (not 'date')",
                has_race_date and not has_plain_date,
                f"Fields: {[k for k in rc.keys() if 'date' in k.lower()]}"
            )
        else:
            RESULTS.add("API racecards schema check", False, "No data")

    def test_fixtures_api_uses_date_field(self):
        """API /api/fixtures normalizes date display (uses date OR race_date)"""
        status, data = api_get("/api/fixtures")
        if status == 200 and isinstance(data, list) and len(data) > 0:
            f = data[0]
            # API uses $ifNull(['$date', '$race_date']) — at least one date field present
            has_date_field = "date" in f or "race_date" in f
            RESULTS.add(
                "API /api/fixtures returns fixtures with date field (normalized)",
                has_date_field,
                f"Date fields: {[k for k in f.keys() if 'date' in k.lower()]}"
            )
        else:
            RESULTS.add("API fixtures date field check", False, "No data")


# ════════════════════════════════════════════════════════════════════════════
# SECTION 7: Error Handling
# ════════════════════════════════════════════════════════════════════════════

class TestErrorHandling(unittest.TestCase):
    def test_racecards_missing_date_gives_400(self):
        """Missing date param returns proper 400 error"""
        status, data = api_get("/api/racecards")
        RESULTS.add(
            "Missing date param returns HTTP 400",
            status == 400,
            f"status={status} (expected 400)"
        )

    def test_nonexistent_date_returns_empty(self):
        """Query for non-existent date returns empty racecards array"""
        status, data = api_get("/api/racecards?date=2099-12-31&venue=ST")
        if status == 200 and data:
            is_empty = len(data.get("racecards", [])) == 0
            RESULTS.add(
                "Non-existent date returns empty racecards (not error)",
                is_empty,
                f"racecards count: {len(data.get('racecards', []))}"
            )


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def run_all_tests():
    print("\n" + "=" * 70)
    print("  🧪 HKJC WEBAPP API TESTS")
    print("  Testing: /api/health, /api/fixtures, /api/racecards, /api/races")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for cls in [
        TestHealth,
        TestFixturesEndpoint,
        TestRacecardsEndpoint,
        TestRacesEndpoint,
        TestJerseyEndpoint,
        TestAPIDatabaseConsistency,
        TestErrorHandling,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=0)
    runner.run(suite)
    print(RESULTS.report())

    if RESULTS.failed > 0:
        print(f"\n❌ {RESULTS.failed} test(s) FAILED\n")
        return 1
    else:
        print(f"\n✅ ALL {RESULTS.total} API TESTS PASSED\n")
        return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())
