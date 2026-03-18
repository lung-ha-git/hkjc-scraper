# Daily Pipeline Flow Document

## Overview

**File**: `daily_pipeline.py`  
**Purpose**: 獨立的每日數據同步與模型訓練系統  
**Trigger**: 系統 cron 或 launchd（**不是** OpenClaw cron）

---

## Architecture

```
daily_pipeline.py (Main)
├── Part 1: Future Race Preparation
│   ├── sync_fixtures()          → src/pipeline/fixtures.py
│   ├── get_next_fixture()       → src/pipeline/fixtures.py
│   └── scrape_race_day()        → src/pipeline/racecards.py
│
└── Part 2: Historical Optimization
    ├── get_past_fixtures()      → src/pipeline/fixtures.py
    ├── get_race_gaps()          → src/pipeline/history.py
    ├── sync_past_race_results() → src/pipeline/history.py
    ├── sync_single_horse()       → src/pipeline/deep_sync.py
    └── train_model_v4.py        (external script)
```

---

## Part 1: Future Race Preparation

### Step 1: Sync Fixtures
```
Input: HKJC 賽程頁面
Output: fixtures collection (比賽日曆)
Module: src/pipeline/fixtures.py
```

### Step 2: Get Next Race Day
```
Input: fixtures collection
Output: next race date + venue
Logic: 搵下一個未來既比賽日
```

### Step 3 & 4: Scrape Racecards
```
Input: race date + venue
Output: racecards + racecard_entries (MongoDB)
Module: src/pipeline/racecards.py
```

**完成後狀態**:
- `fixtures` collection - 有未來賽事日曆
- `racecards` collection - 有排位表 metadata
- `racecard_entries` collection - 有每場既馬匹資料

---

## Part 2: Historical Optimization

### Step 1: Get Past Race Day
```
Input: fixtures collection
Output: 最近過去既比賽日 (過去30日 搵上一次既比賽
```

### Step 2: Gap Analysis內)
Logic:
```
Input: past race date + venue
Output: missing race numbers list
Logic:
  1. 期望場次 = fixture.race_count (通常 8-12 場)
  2. 已存在 = count races collection
  3. missing = 期望 - 已存在
```

### Step 3 & 4: Scrape Missing Results + Horse Data
```
For each missing race:
  1. scrape_race() → src/crawler/race_results_scraper.py
     └── Output: race result, payouts, horse positions
  
  2. upsert_race_result() → races collection
     └── 使用 UPSERT (唔係 delete + insert)
  
  3. For each horse:
     sync_single_horse() → src/pipeline/deep_sync.py
     └── 使用 Upsert 更新:
         - horses (基本資料)
         - horse_race_history (往績)
         - horse_distance_stats (途程)
         - horse_workouts (晨操)
         - horse_medical (傷患)
         - horse_movements (搬遷)
         - horse_overseas (海外)
         - horse_jerseys (彩衣)
```

### Step 5: Train Model (Optional)
```
Input: new race data + horse data
Output: trained model + git push
Script: train_model_v4.py
Steps:
  1. Build training dataset
  2. Train XGBoost model
  3. Evaluate accuracy
  4. Git commit + push
```

---

## Usage

```bash
# 完整流程
python3 daily_pipeline.py

# 跳過模型訓練 (慳時間)
python3 daily_pipeline.py --skip-training

# 測試運行
python3 daily_pipeline.py --dry-run

# 只運行 Part 1 (未來賽事)
python3 daily_pipeline.py --part 1

# 只運行 Part 2 (歷史優化)
python3 daily_pipeline.py --part 2
```

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    daily_pipeline.py                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ PART 1: FUTURE RACE PREPARATION                            │ │
│  ├─────────────────────────────────────────────────────────────┤ │
│  │  1. sync_fixtures()         → fixtures collection          │ │
│  │                             → 賽程日曆                     │ │
│  │                                                             │ │
│  │  2. get_next_fixture()     → next race date/venue         │ │
│  │                                                             │ │
│  │  3. scrape_race_day()      → racecards collection        │ │
│  │                             → racecard_entries collection  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ PART 2: HISTORICAL OPTIMIZATION                            │ │
│  ├─────────────────────────────────────────────────────────────┤ │
│  │  1. get_past_fixtures()     → past race date/venue        │ │
│  │                                                             │ │
│  │  2. Gap Analysis            → missing races list           │ │
│  │     - expected vs found     → missing = expected - found   │ │
│  │                                                             │ │
│  │  3. For each missing race:                                 │ │
│  │     - scrape_race()         → race results + horses       │ │
│  │     - upsert_race_result()  → races collection (UPSERT)   │ │
│  │                                                             │ │
│  │  4. For each horse:                                        │ │
│  │     - sync_single_horse()   → horse_* collections (UPSERT) │ │
│  │                                                             │ │
│  │  5. train_model_v4.py       → train + git push            │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Collections Modified

| Collection | Operation | Description |
|------------|-----------|-------------|
| `fixtures` | UPSERT | 比賽日曆 |
| `racecards` | UPSERT | 排位表 metadata |
| `racecard_entries` | DELETE + INSERT | 排位表馬匹資料 |
| `races` | UPSERT | 賽果 |
| `horses` | UPSERT | 馬匹基本資料 |
| `horse_race_history` | UPSERT | 往績 |
| `horse_distance_stats` | UPSERT | 途程統計 |
| `horse_workouts` | UPSERT | 晨操記錄 |
| `horse_medical` | UPSERT | 傷患記錄 |
| `horse_movements` | UPSERT | 搬遷記錄 |
| `horse_overseas` | UPSERT | 海外賽績 |
| `horse_jerseys` | UPSERT | 彩衣資料 |

---

## Status: COMPLETE ✅

All modules are implemented:
- [x] fixtures.py
- [x] racecards.py  
- [x] history.py
- [x] deep_sync.py
- [x] daily_pipeline.py (main orchestrator)

## TODO / Improvements

### [2026-03-18] 處理多個過去比賽日
**現狀**: Part 2 淨係處理最近既一個比賽日  
**改進**: Loop through 所有過去30日既 fixtures，一次過處理曬

```python
# 改 _get_past_race_day() → _get_all_past_races()
fixtures = get_past_fixtures(days_back=30)

for fixture in fixtures:  # Loop through ALL
    missing = self._gap_analysis(fixture)
    if missing:
        self._scrape_and_sync(missing)
```

**下一步**: 需要 launchd/cron 配置來自動化運行
