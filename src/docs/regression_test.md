# HKJC Scraper Regression Test

## Test Date: 2026-03-09

## Workflow Test Summary

### Phase 1: Jockeys & Trainers
```bash
python3 src/crawler/jockey_trainer_scraper.py
```
- Expected: 43 jockeys, 38 trainers

### Phase 2: Horse List (二字馬)
```bash
python3 extract_erzi_horses.py
# or
python3 src/crawler/horse_list_scraper.py
```
- Expected: 131 horses

### Phase 3: Horse Details
```bash
python3 src/crawler/horse_detail_fixed.py HK_2022_H411
```
- Expected:
  - Horse: 氣勢 (HK_2022_H411)
  - Race history: 20 races
  - Race URLs: 20 unique URLs (extracted from table)
  - Medical: 1 (correct)

### Phase 4: Race Results (Batch)
```bash
# Uses race URLs extracted from horse race history
# Scrapes all unique race URLs
```
- Expected: 21 races, ~240 horse results

## MongoDB Expected Collections

| Collection | Expected Count |
|-----------|----------------|
| jockeys | 43 |
| trainers | 38 |
| horses | 1+ |
| horse_race_history | 20+ |
| horse_medical | 1 |
| races | 21 |
| race_results | 200+ |
| race_payouts | 21 |

## Key Features Tested

1. ✅ Horse detail scraping with URL extraction
2. ✅ Race URL extraction from table (not just race number)
3. ✅ Batch race scraping using URLs
4. ✅ MongoDB storage
5. ✅ Deduplication of race URLs

## Run Full Regression Test

```bash
# Clear MongoDB
mongosh hkjc_racing --eval "db.getCollectionNames().forEach(c => db[c].drop())"

# Phase 1
python3 src/crawler/jockey_trainer_scraper.py

# Phase 2 (get horse list)
python3 extract_erzi_horses.py > /tmp/horse_ids.json

# Phase 3 (scrape horse details)
python3 src/crawler/horse_detail_fixed.py

# Phase 4 (batch scrape races)
# (run the batch script)
```

## Issues Fixed

1. **asyncio.run() in async function** - Use await directly
2. **Race URL extraction** - Get full URL from table, not race number
3. **networkidle timeout** - Changed to domcontentloaded
