# HKJC Complete Scraper Workflow

## Overview

Complete scraper workflow for HKJC horse racing data.

## URL Patterns

| Type | Pattern |
|------|---------|
| Horse List | `https://racing.hkjc.com/zh-hk/local/information/selecthorse` |
| Horse Detail | `https://racing.hkjc.com/zh-hk/local/information/horse?horseid={id}` |
| Race Result | `https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={date}&Racecourse={course}&RaceNo={no}` |
| Jockey | `https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid={id}` |
| Trainer | `https://racing.hkjc.com/zh-hk/local/information/trainerprofile?trainerid={id}` |

## Complete Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: Jockeys & Trainers                                       │
│  - Scrape from jockeyprofile and selecthorse pages                  │
│  - Output: jockeys (40+), trainers (38+)                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: Horse List (二字馬/三字馬/四字馬)                        │
│  - Go to selecthorse page                                          │
│  - Click filters: 二字馬, 三字馬, 四字馬                          │
│  - Extract ALL horse IDs                                           │
│  - Output: ~1000+ horse IDs                                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Horse Details + Race URLs                               │
│  - For each horse:                                                 │
│    - Scrape basic info (name, trainer, color, etc.)              │
│    - Extract race URLs from race history table                    │
│  - Deduplicate race URLs                                           │
│  - Output: horse details, race URLs                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 4: Race Results                                            │
│  - For each unique race URL:                                       │
│    - Scrape race metadata (distance, class, prize, etc.)         │
│    - Extract race results (14 horses per race)                    │
│    - Extract payouts (all pool types)                              │
│    - Extract incidents (race reports)                             │
│  - Output: races, race_results, race_payouts, race_incidents     │
└─────────────────────────────────────────────────────────────────────┘
```

## Usage

```bash
# Run complete workflow
cd hkjc_project
python3 src/crawler/hkjc_complete_scraper.py
```

## MongoDB Collections

| Collection | Description | Key Fields |
|-----------|-------------|------------|
| `jockeys` | All jockeys | jockey_id, name |
| `trainers` | All trainers | trainer_id, name |
| `horses` | Horse basic info | hkjc_horse_id, name, trainer, color, sex |
| `horse_race_history` | Race history | hkjc_horse_id, date, venue, position, jockey, race_url |
| `horse_medical` | Medical records | hkjc_horse_id, count |
| `horse_workouts` | Workout records | hkjc_horse_id, date, details |
| `horse_movements` | Movement records | hkjc_horse_id, date, details |
| `horse_distance_stats` | Distance performance | hkjc_horse_id, distance, wins |
| `races` | Race metadata | _id, race_date, course, race_no, race_id_num, distance, class |
| `race_results` | Race results | race_id, position, horse_id, horse_name, jockey, trainer |
| `race_payouts` | Payouts | race_id, pools |
| `race_incidents` | Race incidents | race_id, horse_id, report |

## Race ID Format

| Field | Format | Example |
|-------|--------|---------|
| `_id` | `YYYY/MM/DD_Course_RaceNo` | `2026/03/08_ST_8` |
| `race_id_num` | HKJC numeric ID | `502` |

## Race Result URL Extraction

Race URLs are extracted directly from the horse's race history table:
- Each row in the race history table contains a link to the race result
- URL format: `?racedate=2026/03/08&Racecourse=ST&RaceNo=10`

## Key Features

1. **Direct URL Extraction**: Race URLs extracted from table, not computed
2. **Deduplication**: Same race from multiple horses = one scrape
3. **Parallel Processing**: Configurable concurrency (default: 2)
4. **Error Handling**: Continues on individual failures
5. **Activity Logging**: All operations logged to MongoDB

## Regression Test

Run full workflow and verify:

```bash
# Clear MongoDB
mongosh hkjc_racing --eval "db.getCollectionNames().forEach(c => db[c].drop())"

# Run scraper
python3 src/crawler/hkjc_complete_scraper.py

# Verify
mongosh hkjc_racing --eval "
print('Jockeys: ' + db.jockeys.countDocuments({}));
print('Trainers: ' + db.trainers.countDocuments({}));
print('Horses: ' + db.horses.countDocuments({}));
print('Races: ' + db.races.countDocuments({}));
print('Race Results: ' + db.race_results.countDocuments({}));
"
```

Expected:
- Jockeys: 40+
- Trainers: 38+
- Horses: 1000+
- Races: 5000+
- Race Results: 70000+

## Files

| File | Description |
|------|-------------|
| `src/crawler/hkjc_complete_scraper.py` | Main scraper |
| `src/crawler/horse_detail_fixed.py` | Horse detail scraper |
| `src/crawler/race_results_scraper.py` | Race result scraper |
| `src/crawler/jockey_trainer_scraper.py` | Jockey/Trainer scraper |

## Author

OpenClaw Agent
Date: 2026-03-09
