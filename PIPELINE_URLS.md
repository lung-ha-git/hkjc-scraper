# HKJC Pipeline — 所有 URLs 列表

*維護者：The_Brain | 更新：2026-03-30*
*用途：Pipeline 使用的所有 HKJC URLs，供 Debugger 和 Tester review*

---

## 快速索引

| # | 用途 | 語言 | Pipeline Part |
|---|------|------|---------------|
| 1 | 賽程表（賽日列表）| EN | Part 1 (Fixtures) |
| 2 | 排位表驗證（場次數）| ZH | Part 1 (Fixtures) |
| 3 | 排位表 GraphQL | — | Part 1 (Racecards) |
| 4 | 排位表備用直連 | ZH | Part 1 (Racecards) |
| 5 | 賽果（單場）| ZH | Part 2 (History) |
| 6 | 賽果（賽日概覽，計數）| ZH | Part 2 (History) |
| 7 | 馬匹資料 | ZH | Part 2 / Part 4 (Deep Sync) |
| 8 | 騎師 Profile | ZH | Part 4 (Queue Worker) |
| 9 | 練馬師 Profile | ZH | Part 4 (Queue Worker) |
| 10 | 練馬師排名 | ZH | Part 4 (Queue Worker) |
| 11 | 騎師排名 | ZH | Part 4 (Queue Worker) |
| 12 | 馬匹列表 | ZH | Part 4 (Queue Worker) |
| 13 | 馬匹途程統計 | ZH | Part 4 (Queue Worker) |

---

## 1. 賽程表 Fixture（賽日列表）

**用於：Part 1 — Fixtures 同步**

```
https://racing.hkjc.com/en-us/local/information/fixture?calyear=2026&calmonth=04
```

**說明：**
- 語言：`en-us`（英文本地賽事，**不包含** overseas 賽事）
- 參數：`calmonth`（不是 `calm`）
- 月份：自動抓取 Sep–Jul 完整賽季（2025-09 到 2026-07）
- 驗證：每個賽日會再抓第 2 項 URL 確認場次數

**驗證每場場次：**
```
https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/04/01&Racecourse=ST
```

**存檔 URL 格式（寫入 `fixtures` collection）：**
```
racecard_url: https://racing.hkjc.com/en-us/local/information/racecard?racedate={YYYY}/{MM}/{DD}&Racecourse={XX}
results_url:  https://racing.hkjc.com/en-us/racing/information/Racing/LocalResults.aspx?RaceDate={YYYY-MM-DD}
```

**⚠️ 注意（2026-03-30）：**
- 原本使用 `zh-hk` + `calm` 參數，會錯誤抓入 overseas 賽事（澳洲/日本等）
- 2026-04-01 原本只顯示 2 場 overseas 賽事（The Roy Higgins + Australian Cup），本地 9 場未出現
- 已修復：改用 `en-us` + `calmonth`

---

## 2. 排位表 Racecard 驗證場次

**用於：Part 1 — `get_race_count_from_racecard()` 驗證**

```
https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={DD/MM/YYYY}&Racecourse={XX}
```

**說明：**
- 只用於計數（統計 `RaceNo=` link 數量，確認場次）
- 不需要登入
- 如果返回「沒有相關資料」，視為 0 場

---

## 3. 排位表 Racecard（GraphQL，實時）

**用於：Part 1 — Racecard 抓取**

```
GraphQL Endpoint:  POST https://info.cld.hkjc.com/graphql/base/
Operation Name:    raceMeetings
Variables:         date (YYYY-MM-DD), venueCode (ST/HV)
Landing Page:      https://bet.hkjc.com/ch/racing/wp/{date}/{venue}/1
```

**說明：**
- Playwright 攔截 `raceMeetings` GraphQL 回應，解析馬匹資料
- **⚠️ 重要限制：** `raceMeetings` 操作返回的是**下一個即將舉行的賽事**，不是歷史賽事
- 對於過去賽日（已有賽果），可能無法從 GraphQL 取到馬匹名單
- 賽日當天可能無 racecard（截止後只顯示賽果）

---

## 4. 排位表 Racecard（Direct HTML，備用）

**用於：Part 1 — Racecard 抓取備用**

```
https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={DD/MM/YYYY}&Racecourse={XX}
```

**說明：**
- 目前未在 pipeline 中被調用（作為 `racecard_scraper.py` 的備用方案）
- 需要 JavaScript 渲染（使用 Playwright）
- `graphql_racecards.js` 攔截 GraphQL，失敗時可 fallback 此 URL

---

## 5. 賽果 Race Results（單場）

**用於：Part 2 — 賽果抓取**

```
https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={DD/MM/YYYY}&Racecourse={XX}&RaceNo={N}
```

**說明：**
- 包含：馬匹名次、馬號、騎師、練馬師、負磅、檔位、距離、完成時間、賠率
- 同時抓取：派彩（Payouts）、競賽事件報告（Incidents）
- URL 模板（Python）：`f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={ddmmyyyy}&Racecourse={venue}&RaceNo={race_no}"`

---

## 6. 賽果賽日概覽（計數場次）

**用於：Part 2 — `_get_actual_race_count()` 確認賽日有多少場**

```
https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={DD/MM/YYYY}
```

**說明：**
- 只用於計數（統計 `RaceNo=` link 數量，確認 `expected_race_count`）
- 比對 `races` collection 現有記錄，找出缺失場次
- 如果返回 404 或無 `RaceNo=` links，視為 0（可能是未來日期或非賽日）

---

## 7. 馬匹資料 Horse Detail

**用於：Part 2 / Part 4**

```
https://racing.hkjc.com/zh-hk/local/information/horse?horseid={HK_XXXX_XXX}
```

**說明：**
- `CompleteHorseScraper` 主 URL
- 包含：基本資料、血統、評分、進口類型、出生地等
- 存檔於 `horses` collection（upsert）

---

## 8. 騎師 Profile

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/information/jockeyprofile?jockeyid={CODE}&season=Current
```

**說明：**
- `JockeyTrainerScraper` 使用
- 存檔於 `jockeys` collection

---

## 9. 練馬師 Profile

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/information/trainerprofile?trainerid={CODE}&season=Current
```

**說明：**
- `JockeyTrainerScraper` 使用
- 存檔於 `trainers` collection

---

## 10. 練馬師排名

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/info/trainer-ranking?season=Current&view=Numbers&racecourse=ALL
```

**說明：**
- `RankingScraper` 使用
- 存檔於 `trainers` collection

---

## 11. 騎師排名

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/info/jockey-ranking?season=Current&view=Numbers&racecourse=ALL
```

**說明：**
- `RankingScraper` 使用
- 存檔於 `jockeys` collection

---

## 12. 馬匹列表

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/information/selecthorse
```

**說明：**
- `HorseListScraper` 使用
- 列出所有 HKJC 馬匹名單

---

## 13. 馬匹途程統計

**用於：Part 4 (Queue Worker)**

```
https://racing.hkjc.com/zh-hk/local/information/ratingresultweight?horseid={HK_XXXX_XXX}
```

**說明：**
- `CompleteHorseScraper` 內部調用
- 存檔於 `horse_distance_stats` collection

---

## Pipeline URL 流向圖

```
Part 1: Fixtures
  calendar page ──► racecard page (verify race count)
  fixture record ──► stored in fixtures collection

Part 1: Racecards
  GraphQL (raceMeetings) ──► racecards + racecard_entries collections
  ↓ fallback (if needed)
  Direct HTML racecard page

Part 2: History
  Results overview page ──► count expected races
  ↓ gap analysis
  Results per-race page ──► races + race_results + race_payouts + race_incidents
  ↓ for each horse
  Horse detail page ──► horses + horse_medical + horse_movements + horse_workouts

Part 3: Completeness
  racecard_entries ──► check horses collection completeness
  ↓ incomplete horses
  scrape_queue

Part 4: Queue Worker
  scrape_queue ──► horse_detail / jockey / trainer / ranking scrapers
```

---

## 賽果數量問題（用戶反饋）

**觀察（2026-03-28 pipeline log）：**
- Pipeline 報告 `races collection` 賽果數量可能少於預期
- `_get_actual_race_count()` 從賽果概覽頁面計數 `RaceNo=` links

**可能的 Gap 原因：**

| # | 可能原因 | 檢查方法 |
|---|---------|---------|
| 1 | 賽果頁面 JS 渲染延遲 | `_get_actual_race_count()` 計數失敗，返回 0 |
| 2 | 參數格式：DD/MM/YYYY vs YYYY/MM/DD | URL 需要 `DD/MM/YYYY`（`2026/03/25`）|
| 3 | 非賽日被計入（HV+ST 同日）| 同一天兩個 venue 各自獨立計數 |
| 4 | 歷史資料庫已有但未更新 | `races` collection 有舊記錄但 `payout` 為空 |

**建議 Debug 方法：**
```python
# 直接測試 URL 格式
url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/25"
# 確認有 9 個 RaceNo= links
```

---

## 歷史記錄

| 日期 | 更新 |
|------|------|
| 2026-03-30 | 創建本文檔；修正 #1 FIXTURE_URL：`zh-hk` → `en-us`，`calm` → `calmonth` |
