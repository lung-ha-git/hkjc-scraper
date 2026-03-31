# HKJC Data Sync Workflow

## Overview

This document describes the data synchronization workflow for HKJC horse racing data.

## Data Sources

| Source | URL | Update Frequency |
|--------|-----|-----------------|
| Fixture (Calendar) | `https://racing.hkjc.com/zh-hk/local/information/fixture` | Monthly |
| Race Card | `https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={date}&Racecourse={venue}` | Daily check |
| Race Results | `https://racing.hkjc.com/zh-hk/racing/information/English/Racing/LocalResults.aspx?RaceDate={date}` | Daily |
| Jockey Rankings | `https://racing.hkjc.com/zh-hk/local/info/jockey-ranking?season=Current&view=Numbers&racecourse=ALL` | Weekly |
| Trainer Rankings | `https://racing.hkjc.com/zh-hk/local/info/trainer-ranking?season=Current&view=Numbers&racecourse=ALL` | Weekly |

## Workflow

### Step 1: Download Fixture (Monthly)

```bash
python -m src.crawler.fixture_scraper
```

Process:
1. Fetch fixture page for each month (Sep-Jul season)
2. Parse race meetings: date, venue, race count
3. Save to MongoDB `fixtures` collection

**Output:** `fixtures` collection with 99 race meetings per season

### Step 2: Daily Sync (06:00)

```bash
python -m src.scheduler.sync_scheduler
```

Process:
1. Query next race day from `fixtures` where `scrape_status = 'pending'`
2. Check racecard page has data:
   - URL: `racecard?racedate={date}&Racecourse={venue}`
   - If returns "沒有相關資料" → skip (not published yet)
3. If has data:
   - Add race to `race_queue` (race_result items)
   - For each race, add horse items to `scrape_queue`
   - Add jockey/trainer items to respective queues
4. Update `fixtures.scrape_status = 'queued'`

### Step 3: Scraping Cron (09:00)

```bash
python -m src.scheduler.queue_worker
```

Process:
1. Query pending queue items where `scheduled_time <= now()`
2. Execute scraper based on `type`:
   - `race_result` → Race results scraper
   - `horse_detail` → Horse detail scraper  
   - `jockey_detail` → Jockey scraper
   - `trainer_detail` → Trainer scraper
3. Update item status: `completed` / `failed`
4. Retry failed items (max 3 retries)

## Queue Structure

### race_queue
```json
{
  "type": "race_result",
  "target_url": "https://racing.hkjc.com/zh-hk/.../LocalResults.aspx?RaceDate=2026-03-15",
  "race_date": "2026-03-15",
  "venue": "ST",
  "race_no": 1,
  "scheduled_scrape_time": "2026-03-16T09:00:00",
  "status": "pending",
  "retry_count": 0,
  "created_at": "2026-03-15T06:00:00",
  "modified_at": "2026-03-15T06:00:00"
}
```

### scrape_queue (Horse Details)
```json
{
  "type": "horse_detail",
  "target_url": "https://racing.hkjc.com/zh-hk/local/information/horse?horseid=H001",
  "horse_id": "H001",
  "race_date": "2026-03-15",
  "scheduled_scrape_time": "2026-03-16T09:00:00",
  "status": "pending",
  "retry_count": 0,
  "created_at": "2026-03-15T06:00:00",
  "modified_at": "2026-03-15T06:00:00"
}
```

### jockey_queue / trainer_queue
```json
{
  "type": "jockey_detail",
  "target_url": "https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid=PZ",
  "jockey_id": "PZ",
  "scheduled_scrape_time": "2026-03-16T09:00:00",
  "status": "pending",
  "retry_count": 0,
  "created_at": "2026-03-15T06:00:00",
  "modified_at": "2026-03-15T06:00:00"
}
```

## Cron Setup

```bash
# Daily sync (06:00)
0 6 * * * cd /path/to/hkjc_project && python -m src.scheduler.sync_scheduler >> logs/sync.log 2>&1

# Daily scraping (09:00)
0 9 * * * cd /path/to/hkjc_project && python -m src.scheduler.queue_worker >> logs/scraper.log 2>&1

# Weekly jockey/trainer update (Monday 05:00)
0 5 * * 1 cd /path/to/hkjc_project && python -m src.crawler.ranking_scraper >> logs/ranking.log 2>&1

# Monthly fixture update (1st of month 04:00)
0 4 1 * * cd /path/to/hkjc_project && python -m src.crawler.fixture_scraper >> logs/fixture.log 2>&1
```

## Collections

| Collection | Description |
|------------|-------------|
| `fixtures` | Race meeting calendar (99 records/season) |
| `race_queue` | Pending race result scrapes |
| `scrape_queue` | Pending horse detail scrapes |
| `jockey_queue` | Pending jockey detail scrapes |
| `trainer_queue` | Pending trainer detail scrapes |
| `horses` | Horse master data |
| `races` | Race results |
| `jockeys` | Jockey statistics |
| `trainers` | Trainer statistics |

## Implementation Status

| Component | Status |
|-----------|--------|
| Fixture Scraper | ✅ Done (`src/crawler/fixture_scraper.py`) |
| Ranking Scraper (Jockey/Trainer) | ✅ Done (`src/crawler/ranking_scraper.py`) |
| Race Card Checker | ✅ Done (in sync_scheduler) |
| Sync Scheduler | ✅ Done (`src/scheduler/sync_scheduler.py`) |
| Queue Worker | ✅ Done (`src/scheduler/queue_worker.py`) |

## Notes

- Race cards are typically published 1-2 days before race day
- Past race results may not be immediately available on racecard page
- Use race results page for historical data
- HV (跑馬地) venues may need manual verification in fixtures
