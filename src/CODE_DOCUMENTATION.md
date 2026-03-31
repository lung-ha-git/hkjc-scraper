# HKJC Racing Project - Code Documentation

## 📁 Project Structure

```
hkjc_project/
├── src/
│   ├── crawler/          # Web scraping modules
│   ├── database/          # Database connections
│   ├── etl/              # ETL pipeline
│   ├── ml/               # ML model training
│   ├── scheduler/        # Queue workers & schedulers
│   └── utils/            # Utilities
├── config/               # Configuration
├── tests/                # Test files
├── scripts/              # Utility scripts
└── web-app/              # Web application
```

---

## 📄 File Overview & Functions

### 1. Crawler Modules (`src/crawler/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `hkjc_scraper.py` | Basic race results scraper (requests) | `get_race_results()`, `get_recent_results()`, `_parse_race_table()` |
| `hkjc_complete_scraper.py` | Complete scraper combining multiple sources | `scrape_complete()`, `_extract_*()` |
| `race_results_scraper.py` | **Main race results scraper (Playwright)** | `scrape_race()`, `_scrape_results_table()`, `_scrape_payouts_table()`, `_scrape_incidents_table()` |
| `race_results_parser.py` | Parse race results HTML | `parse_race_html()` |
| `complete_horse_scraper.py` | **Complete horse detail scraper** | `scrape_horse_complete()`, `_extract_basic_info()`, `_extract_race_history_complete()`, `_extract_distance_stats()`, `_extract_workouts()`, `_extract_medical()`, `_extract_movements()`, `_extract_overseas()`, `_extract_jersey()` |
| `horse_list_scraper.py` | Get list of all horses from HKJC | `get_all_horse_ids()`, `_extract_horse_links()`, `filter_by_name_length()`, `get_all_trainers_horses()` |
| `horse_detail_scraper.py` | Horse detail page scraper | `scrape_horse()` |
| `horse_detail_fixed.py` | Fixed version of horse detail scraper | Similar to above with fixes |
| `horse_distance_scraper.py` | Horse distance performance scraper | `scrape_distance_data()` |
| `horse_tabs_fixed.py` | Fixed tab-based horse data scraper | `scrape_tabs()` |
| `jockey_trainer_scraper.py` | Jockey/Trainer info scraper | `scrape_jockey()`, `scrape_trainer()` |
| `ranking_scraper.py` | **Jockey & Trainer ranking scraper** | `scrape_jockeys()`, `scrape_trainers()`, `save_to_mongodb()` |
| `fixture_scraper.py` | Race fixture/scchedule scraper | `scrape_fixture()` |
| `overall_scraper.py` | Overall statistics scraper | `scrape_overall()` |
| `playwright_scraper.py` | Base Playwright scraper | Common playwright utilities |
| `hkjc_precise_scraper.py` | Precise targeting scraper | `scrape_with_precision()` |
| `test_h432.py`, `check_h432_medical.py` | Testing/debug scripts | Test functions |

### 2. Database Modules (`src/database/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `connection.py` | **MongoDB connection manager** | `connect()`, `disconnect()`, `get_collection()`, `create_indexes()`, `get_stats()` |
| `models.py` | Database models/schemas | Pydantic models for data validation |
| `setup_db.py` | Database setup script | `setup_database()` |
| `sqlite_connection.py` | SQLite connection (alternative) | SQLite specific operations |

### 3. ETL Pipeline (`src/etl/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `pipeline.py` | **ETL pipeline for race data** | `process_race()`, `_process_runners()`, `load_races()`, `run()` |

### 4. ML Modules (`src/ml/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `model_trainer.py` | **ML model trainer (XGBoost/RF)** | `train_place_model()`, `train_win_model()`, `prepare_features()`, `evaluate_model()`, `cross_validate()` |
| `training_data.py` | Build training datasets | `build_place_dataset()`, `build_win_dataset()` |
| `feature_engineer.py` | Feature engineering | `create_features()` |
| `weighted_scorer.py` | Weighted scoring system | `calculate_score()` |

### 5. Scheduler Modules (`src/scheduler/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `queue_worker.py` | **Queue worker for scraping jobs** | `process_queue()`, `scrape_race_result()`, `scrape_horse_detail()`, `_save_horse_complete()` |
| `sync_scheduler.py` | Synchronous scheduler | `schedule_jobs()` |

### 6. Utils Modules (`src/utils/`)

| File | Description | Key Functions |
|------|-------------|---------------|
| `validators.py` | Data validation | `validate_race()`, `validate_horse()` |
| `clean_horse_data.py` | Data cleaning | `clean_horse()` |
| `scraping_queue.py` | Queue management | `add_to_queue()`, `get_next_job()` |
| `scraper_activity_log.py` | Activity logging | `log_activity()` |
| `mock_data.py` | Mock data for testing | `generate_mock_horse()` |

---

## 🔄 Main Data Flows

### Flow 1: Race Results Scraping
```
User/API → RaceResultsScraper → HKJC Website → Parse HTML → 
MongoDB (races, race_results, race_payouts, race_incidents)
```

**Key Steps:**
1. `RaceResultsScraper.scrape_race(date, venue, race_no)`
2. `_scrape_race_metadata()` - Get race info (class, distance, prize)
3. `_scrape_results_table()` - Get horse results (position, odds, time)
4. `_scrape_payouts_table()` - Get payout pools (WIN, PLACE, QUINELLA)
5. `_scrape_incidents_table()` - Get incident reports
6. `save_to_mongodb()` - Save to collections

### Flow 2: Complete Horse Data Scraping
```
Horse List → CompleteHorseScraper → HKJC Horse Page → 
Parse all tabs → MongoDB (horses, horse_race_history, horse_distance_stats, 
                          horse_workouts, horse_medical, horse_movements, horse_overseas)
```

**Key Steps:**
1. `HorseListScraper.get_all_horse_ids()` - Get all horse IDs
2. `CompleteHorseScraper.scrape_horse_complete(horse_id)`
3. Extract data from 8 tabs:
   - Basic Info (name, age, sex, trainer, owner, pedigree)
   - Race History (past performances with rating/weight)
   - Distance Stats (performance by distance)
   - Workouts (晨操記錄)
   - Medical (傷患紀錄)
   - Movements (搬遷記錄)
   - Overseas (海外賽績)
   - Jersey (彩衣)
4. `_save_to_mongodb()` - Upsert to collections (using safe_upsert to avoid overwriting)

### Flow 3: Queue-Based Scraping
```
Scheduler → Queue → QueueWorker → 
  ├── RaceResultsScraper (race_result)
  ├── CompleteHorseScraper (horse_detail)
  └── RankingScraper (jockey_detail, trainer_detail)
```

**Key Steps:**
1. Jobs added to queue (race_queue, scrape_queue, jockey_queue, trainer_queue)
2. `QueueWorker.process_queue()` fetches pending items
3. `process_item()` routes to appropriate scraper
4. Results saved with upsert (safe_upsert for horse sub-collections)

### Flow 4: Jockey/Trainer Ranking Update
```
RankingScraper → HKJC Ranking Page → Parse Table → MongoDB (jockeys, trainers)
```

**Key Steps:**
1. `RankingScraper.scrape_jockeys()` - Get current season stats
2. `RankingScraper.scrape_trainers()` - Get trainer stats
3. Match with existing IDs
4. `save_to_mongodb()` - Update collections

### Flow 5: ETL Pipeline
```
Raw Race Data → ETLPipeline.process_race() → Validation → 
Transform → MongoDB (races)
```

**Key Steps:**
1. `validate_race()` - Check required fields
2. Transform data format (dates, numeric fields)
3. `_process_runners()` - Clean runner data
4. `load_races()` - Upsert to MongoDB

### Flow 6: ML Model Training
```
Database → TrainingDataBuilder → Feature Engineering → 
ModelTrainer → XGBoost/RandomForest → Evaluation → Save Model
```

**Key Steps:**
1. `TrainingDataBuilder.build_place_dataset()` - Build training data
2. `prepare_features()` - Encode categorical, scale numeric
3. `train_xgboost()` or `train_random_forest()` - Train model
4. `evaluate_model()` - Get accuracy, precision, recall, AUC
5. Feature importance analysis

---

## 🗄️ MongoDB Collections

| Collection | Description | Key Fields |
|------------|-------------|------------|
| `races` | Race metadata | race_id, date, venue, race_no, distance, class, prize |
| `race_results` | Race results per horse | race_id, horse_id, position, odds, finish_time |
| `race_payouts` | Payout pools | race_id, pools (WIN, PLACE, QUINELLA...) |
| `race_incidents` | Incident reports | race_id, horse_id, report |
| `horses` | Horse basic info | hkjc_horse_id, name, age, sex, trainer, owner, pedigree |
| `horse_race_history` | Past race performances | hkjc_horse_id, race_date, position, rating, weight |
| `horse_distance_stats` | Distance performance | hkjc_horse_id, course_type, distance, wins/place stats |
| `horse_workouts` | Morning workout records | hkjc_horse_id, date, venue, distance, time |
| `horse_medical` | Vet/medical records | hkjc_horse_id, date, issue, treatment |
| `horse_movements` | Relocation records | hkjc_horse_id, date, from, to |
| `horse_overseas` | Overseas race records | hkjc_horse_id, date, country, position |
| `jockeys` | Jockey stats | jockey_id, name, wins, total_rides, prize_money |
| `trainers` | Trainer stats | trainer_id, name, wins, total_horses, prize_money |

---

## 🚀 How to Run

### Scrape a Race
```python
from src.crawler.race_results_scraper import RaceResultsScraper

async def main():
    async with RaceResultsScraper() as scraper:
        result = await scraper.scrape_race("2026/03/01", "ST", 7)
        await scraper.save_to_mongodb(result)
```

### Scrape a Horse
```python
from src.crawler.complete_horse_scraper import CompleteHorseScraper

scraper = CompleteHorseScraper()
result = await scraper.scrape_horse_complete("HK_2023_J256")
```

### Run Queue Worker
```python
from src.scheduler.queue_worker import QueueWorker

worker = QueueWorker()
await worker.run()
```

### Train ML Model
```python
from src.ml.model_trainer import ModelTrainer

trainer = ModelTrainer()
place_model, results = trainer.train_place_model()
```

---

## ⚠️ Important Notes

1. **Queue Worker Principle**: Always use `upsert` instead of `delete + insert` to avoid overwriting existing correct data
2. **Safe Upsert**: Use `safe_upsert()` helper that checks for valid data before updating
3. **Anti-bot Measures**: Use user-agent rotation, rate limiting, and random delays
4. **Phase 5**: Jockey/Trainer data comes from `RankingScraper`, not individual detail scrapers

---

*Last updated: 2026-03-17*
