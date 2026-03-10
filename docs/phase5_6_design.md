# Phase 5 & 6 Design Doc

## Phase 5: 補 Jockey & Trainer 資料 + Horse Silks

### 現有數據結構

**jockeys collection:**
```json
{
  "_id": ObjectId,
  "name": "潘頓",
  "link": "/zh-hk/local/information/jockey?jockeycode=PEN",
  "jockey_code": "PEN"
}
```

**trainers collection:**
```json
{
  "_id": ObjectId,
  "name": "蔡約翰",
  "link": "/zh-hk/local/information/trainer?trainercode=JJL",
  "trainer_code": "JJL"
}
```

### 目標數據結構

**horses collection (新增):**
```json
{
  "_id": ObjectId,
  "hkjc_horse_id": "HK_2024_K305",
  "name": "林寶精神",
  "horse_code": "K305",  // 烙號
  
  // 彩衣 (新增)
  "jersey_url": "https://racing.hkjc.com/racing/content/Images/RaceColor/K305.gif"
}
```

**彩衣 URL Pattern:**
```
https://racing.hkjc.com/racing/content/Images/RaceColor/{烙號}.gif
https://racing.hkjc.com/racing/content/Images/RaceColor/{烙號}_80x60.gif (thumbnail)
```

**jockeys collection (更新):**
```json
{
  "_id": ObjectId,
  "name": "潘頓",
  "jockey_code": "PEN",
  
  // 基本資料
  "chinese_name": "潘頓",
  "english_name": "Purton",
  "birth_date": "1974-09-13",
  
  // 統計數據
  "total_wins": 1234,
  "season_wins": 45,
  "total_rides": 5678,
  "win_rate": 21.7,
  "place_rate": 55.2,
  
  // 現時評分
  "current_rating": 132,
  
  // 近10場成績
  "recent_10": [
    {"date": "2026-03-08", "position": 1, "horse": "馬名", "odds": 3.2},
    {"date": "2026-03-01", "position": 2, "horse": "馬名", "odds": 5.5}
  ],
  
  // 檔位統計
  "draw_stats": {
    "1": {"wins": 12, "runs": 45},
    "2": {"wins": 8, "runs": 42}
  },
  
  //  biography
  "bio": "來自澳洲..."
}
```

**trainers collection (更新):**
```json
{
  "_id": ObjectId,
  "name": "蔡約翰",
  "trainer_code": "JJL",
  
  // 基本資料
  "chinese_name": "蔡約翰",
  "english_name": "John Size",
  
  // 統計數據
  "total_wins": 892,
  "season_wins": 34,
  "total_runs": 4567,
  "win_rate": 19.5,
  "place_rate": 52.1,
  
  // 馬房資料
  "stable_location": "跑馬地",
  "total_horses": 28,
  
  // 近10場成績
  "recent_10": [...],
  
  // Biography
  "bio": "來自英國..."
}
```

### URLs

**Jockey:**
```
https://racing.hkjc.com/zh-hk/local/information/jockey?jockeycode=PEN
```

**Trainer:**
```
https://racing.hkjc.com/zh-hk/local/information/trainer?trainercode=JJL
```

### Scraping 方法

1. 從現有 `jockeys`/`trainers` collection 拎 code
2. Loop 每個 code，去對應 URL
3. Parse 數據並 update collection

---

## Phase 6: 新本地賽事 Scrap

### 目標
- 定期爬取最新賽事結果
- 每日/每週自動更新
- 避免重複爬取

### 數據來源

| URL | 用途 |
|-----|------|
| `racing.hkjc.com/zh-hk/local/raceinformation` | 賽期表 |
| `.../localresults?racedate=2026/03/10&Racecourse=ST` | 賽果 |
| `.../racecard?racedate=2026/03/10&Racecourse=ST` | 排位表 |

### 新增 Collection: `race_schedule`

```json
{
  "_id": ObjectId,
  "race_date": "2026-03-10",
  "venue": "ST",  // ST or HV
  
  // 賽事列表
  "races": [
    {
      "race_no": 1,
      "time": "13:00",
      "class": "4",
      "distance": 1200,
      "track": "草地",
      "prize": "$1,200,000"
    },
    ...
  ],
  
  // Metadata
  "scraped_at": "2026-03-10T14:00:00Z",
  "status": "completed"  // upcoming, completed
}
```

### 流程

```
1. 拎今日/明日賽期
   GET raceinformation
   
2. 檢查邊啲賽事已經有結果
   compare with races collection
   
3. 如果有新賽事，去拎結果
   GET localresults?racedate=xxx&Racecourse=xxx
   
4. 更新 races collection
```

### Storage 優化

**races collection 新增 fields:**
```json
{
  "hkjc_race_id": "2026_03_10_ST_1",
  "race_date": "2026-03-10",
  "venue": "ST",
  "race_no": 1,
  ...
  
  // 新增
  "scraped_at": "2026-03-10T18:00:00Z",
  "last_updated": "2026-03-10T18:00:00Z"
}
```

### Cron Job (可選)

```bash
# 每日 8pm 自動爬
0 20 * * * cd /path/to/project && python3 scraper.py --phase6
```

---

## 總結

| Phase | 功能 | Collections |
|-------|------|-------------|
| Phase 1-3 | Horse 基本數據 | horses, horse_race_history, etc. |
| Phase 4 | Race Results | races |
| Phase 5 | Jockey/Trainer 詳細 | jockeys, trainers |
| Phase 6 | 持續更新 | races (新增 field) |
