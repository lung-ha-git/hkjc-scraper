# Scraper Test Results

## Test Date: 2026-03-12

---

## 1. Race Results Scraper ✅ WORKING

**Status:** Success
- Scraped: 2026/03/15 Race 1
- Results: 12 horses
- Payouts: 10 pools

**MongoDB Structure (races collection):**
```
Fields: _id, hkjc_race_id, class, distance, results[], payout{}, 
        incidents[], track_condition, venue, race_date, race_no
```

---

## 2. Horse Detail Scraper ⚠️ ISSUES

**Status:** Returns empty data (name=None)

**Issue:** The scraper returns different structure than MongoDB

**MongoDB Structure (horses collection):**
```
Fields: hkjc_horse_id, name, age, color, sex, trainer, owner, 
        sire, dam, import_type, country_of_origin, total_prize, 
        career_wins, career_starts, etc.
```

**Scraper Returns:**
```
{
  "hkjc_horse_id": "HK_2025_L108",
  "pedigree": {},
  "stats": {},
  "season_info": {}
}
```

---

## 3. Jockey Scraper ⚠️ ISSUES

**Status:** Returns page title instead of data

**MongoDB Structure (jockeys collection):**
```
Fields: jockey_id, name, wins, seconds, thirds, fifths, fourths,
        total_rides, prize_money, prize_money_int, season
```

**Scraper Returns:**
```
{"jockey_id": "PZ", "name": "首頁 English"}  # Wrong!
```

---

## 4. Trainer Scraper ⚠️ ISSUES

**Status:** Same as jockey - returns wrong data

**MongoDB Structure (trainers collection):**
```
Fields: trainer_id, name, wins, seconds, thirds, fifths, fourths,
        total_horses, prize_money, prize_money_int, season
```

---

## Summary

| Scraper | Status | Notes |
|----------|--------|-------|
| Race Results | ✅ Working | Data saves correctly |
| Horse Detail | ⚠️ Issues | Returns different format |
| Jockey | ⚠️ Issues | Regex parsing problem |
| Trainer | ⚠️ Issues | Same as jockey |

## Recommendations

1. **Race Results** - No changes needed
2. **Horse Detail** - Need to map scraper output to MongoDB fields
3. **Jockey/Trainer** - Need to fix regex parsing in scraper

The Phase 5 ranking scraper already populates jockeys/trainers with the correct structure. The detail scrapers in jockey_trainer_scraper.py have parsing issues.
