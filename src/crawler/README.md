# HKJC Crawler - 文件結構說明

## 主要檔案 (Main Files)

### 1. hkjc_complete_scraper.py ⭐ 主要爬蟲
**用途**: 完整爬蟲流程管理
- Phase 1: Jockeys & Trainers
- Phase 2: Horse List (二字馬)
- Phase 3: Horse Details + Race URLs
- Phase 4: Race Results

**使用方法**:
```bash
python3 src/crawler/hkjc_complete_scraper.py --show-log   # 查看進度
python3 src/crawler/hkjc_complete_scraper.py --no-resume  # 從頭開始
python3 src/crawler/hkjc_complete_scraper.py -c 3         # 調整並發數
```

### 2. horse_all_tabs_scraper.py 
**用途**: 爬取馬匹所有分頁數據
- 往績紀錄 (race_history)
- 所跑途程 (distance_stats)
- 晨操紀錄 (workouts)
- 傷患紀錄 (medical)
- 搬遷紀錄 (movements)
- 海外賽績 (overseas)
- 血統簡評 (pedigree)
- 馬匹評分 (horse_ratings)

**被引用**: hkjc_complete_scraper.py (Phase 3 中使用)

---

## 閒置檔案 (Unused - 可刪除)

這些檔案是早期開發版本，已被 hkjc_complete_scraper.py 取代：

| 檔案 | 狀態 | 說明 |
|------|------|------|
| complete_horse_scraper.py | ❌ 閒置 | 早期版本 |
| complete_horse_system.py | ❌ 閒置 | 早期版本 |
| hkjc_scraper.py | ❌ 閒置 | 早期版本 |
| hkjc_precise_scraper.py | ❌ 閒置 | 早期版本 |
| horse_detail_scraper.py | ❌ 閒置 | 早期版本 |
| horse_detail_fixed.py | ❌ 閒置 | 早期版本 |
| horse_list_scraper.py | ❌ 閒置 | 早期版本 |
| horse_tabs_fixed.py | ❌ 閒置 | 早期版本 |
| horse_quick_test.py | ❌ 閒置 | 測試檔案 |
| jockey_trainer_scraper.py | ❌ 閒置 | 功能已整合 |
| overall_scraper.py | ❌ 閒置 | 早期版本 |
| race_results_scraper.py | ❌ 閒置 | 閒置 |
| race_results_parser.py | ❌ 閒置 | 閒置 |
| check_h432_medical.py | ❌ 閒置 | 測試檔案 |
| collect_zhuyuan_fixed.py | ❌ 閒置 | 測試檔案 |
| playwright_scraper.py | ❌ 閒置 | 基礎框架 |
| test_h432.py | ❌ 閒置 | 測試檔案 |

---

## 依賴關係

```
hkjc_complete_scraper.py
    ├── horse_all_tabs_scraper.py  (被引用)
    ├── src/database/connection.py  (MongoDB)
    └── src/utils/scraper_activity_log.py  (進度追蹤)
```

---

## 數據流向

```
HKJC Website
    │
    ▼
hkjc_complete_scraper.py (主流程)
    │
    ├─► Phase 1: jockeys, trainers
    │
    ├─► Phase 2: horse_ids (二字馬)
    │
    ├─► Phase 3: horse details
    │       │
    │       ├─► horses collection
    │       ├─► horse_race_history
    │       ├─► horse_distance_stats
    │       ├─► horse_workouts
    │       ├─► horse_medical
    │       ├─► horse_movements
    │       ├─► horse_overseas
    │       ├─► horse_pedigree
    │       └─► horse_ratings
    │
    └─► Phase 4: race results
            │
            └─► races collection
```

---

## 清理建議

如需清理閒置檔案：
```bash
cd src/crawler/
# 移動到 archive 目錄 (不刪除)
mkdir -p archive
mv complete_horse_scraper.py complete_horse_system.py hkjc_scraper.py archive/
# ... 其他閒置檔案
```
