# HKJC Data Pipeline System

## Overview

Automated daily data sync and model training pipeline for HKJC horse racing data.

## Architecture

```
src/pipeline/
├── runner.py          # Main orchestrator
├── fixtures.py        # Race calendar sync
├── racecards.py       # Race card scraping  
├── history.py         # Past results sync
├── deep_sync.py       # Horse data deep sync
└── __init__.py
```

## Pipelines

### 1. Future Prediction Pipeline
```bash
python3 -m src.pipeline.runner --pipeline future
```
- Sync fixtures (calendar)
- Scrape next race day racecards

### 2. Historical Optimization Pipeline
```bash
python3 -m src.pipeline.runner --pipeline history
```
- Check past race days
- Gap analysis (find missing results)
- Incremental scrape missing results
- Deep sync horse data

### 3. Full Pipeline (Daily)
```bash
python3 -m src.pipeline.runner --pipeline all
```
- All of the above

## Individual Commands

```bash
# Sync race fixtures
python3 -m src.pipeline.runner --pipeline fixtures

# Scrape next racecards
python3 -m src.pipeline.runner --pipeline racecards

# Sync past results
python3 -m src.pipeline.runner --pipeline history

# Deep sync horse data
python3 -m src.pipeline.runner --pipeline deep-sync
```

## Cron Setup

```bash
# Setup recommended cron jobs
./scripts/setup_cron.sh

# Or run manually
./scripts/run_pipeline.sh --pipeline all
```

### Recommended Cron Schedule

| Time | Pipeline | Purpose |
|------|----------|---------|
| 5:00 AM | fixtures | Sync race calendar |
| 6:00 AM | racecards | Scrape next race day |
| 7:00 AM | history | Sync past results |
| 2:00 AM (Sun) | deep-sync | Deep horse data sync |

## Database Collections

### Fixtures
- `fixtures` - Race meeting calendar

### Race Data
- `racecards` - Race metadata
- `racecard_entries` - Horse entries per race
- `races` - Race results

### Horse Data
- `horses` - Horse basic info
- `horse_race_history` - Race history
- `horse_distance_stats` - Distance statistics
- `horse_workouts` - Training records
- `horse_medical` - Medical records
- `horse_movements` - Stable movements
- `horse_ratings` - Rating history

## Key Principles

1. **Upsert Only** - Never delete + insert. Use update + upsert for data consistency.
2. **Idempotent** - Can run multiple times safely.
3. **Dry Run** - Always test with `--dry-run` first.
4. **Rate Limiting** - Respect HKJC servers with delays between requests.

## Environment

- Default: `hkjc_racing_dev` (development)
- Set `MONGODB_DB_NAME=hkjc_racing` for production
