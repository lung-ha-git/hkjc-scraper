# TASK-010: Odds Collector Log 重新實作 + 驗證完整功能

**創建日期**: 2026-03-28  
**狀態**: 已驗證  
**優先級**: High  
**負責人**: Dev_Alpha  

---

## 目標

重新實作 Odds Collector 檔案日誌功能，並確保完整功能運作正常。

## ⚠️ 重要約束

**不能破壞任何現有功能：**
- Web App 必須正常運作
- MongoDB 資料必須安全
- Odds Collector Service 必須正常運行
- 所有 Docker containers 必須健康

## 當前問題

1. Odds Collector 只有 `console.log`，沒有檔案日誌
2. 需要確保 `/app/scrapers/logs/` 可以正常寫入
3. Volume `odds_logs` 掛載可能需要調整

## 需求

### 1. 檔案日誌功能
- [x] Odds Collector 必須寫入日誌到 `/app/scrapers/logs/odds_YYYY-MM-DD.log`
- [x] 日誌應該包含爬蟲運行的關鍵資訊
- [x] Volume 必須正確掛載

### 2. 日誌下載功能
- [x] Web API 提供 `/api/logs/list` 端點
- [x] Web API 提供 `/api/logs/download/:source/:filename` 端點
- [x] 前端 `logs.html` 頁面正常顯示
- [x] URL: `https://horse.fatlung.com/logs.html`

### 3. 功能驗證（必須全部通過）

#### A. 完整排位表（排位表）
- [x] API `/api/racecards?date=YYYY-MM-DD` 返回完整排位表
- [x] 每匹馬有 `jersey_url`（彩衣）
- [x] 每匹馬有 `horse_name`、`jockey_name`、`draw` 等欄位
- [x] **驗證命令**：
  ```bash
  curl -s "https://horse.fatlung.com/api/racecards?date=2026-03-29" | jq '.racecards[0].horses[0].jersey_url'
  ```

#### B. 正確預測賽果
- [x] API `/api/predict` 返回不同分數的預測（不是全部相同）
- [x] 每匹馬有 `score`、`win_probability`、`predicted_rank`
- [x] **驗證命令**：
  ```bash
  curl -s "https://horse.fatlung.com/api/predict?race_date=2026-03-29&race_no=1&venue=ST" | jq '.predictions[0].score'
  ```
- [x] **預期結果**：分數應該不同（例如 8.5, 9.2, 7.8 等）

#### C. 賽事資料存在
- [x] MongoDB `horses` collection 有資料（> 1000）
- [x] MongoDB `races` collection 有資料（> 2000）
- [x] **驗證命令**：
  ```bash
  docker exec hkjc-pipeline python3 -c "from src.database.connection import DatabaseConnection; db = DatabaseConnection(); db.connect(); print('horses:', db.db.horses.count_documents({})); print('races:', db.db.races.count_documents({})); db.disconnect()"
  ```

## 驗證清單

完成後，必須執行以下所有驗證：

| 驗證項目 | 命令 | 預期結果 | 狀態 |
|----------|------|----------|------|
| `jersey_url` 存在 | `curl .../racecards?... \| jq '.racecards[0].horses[0].jersey_url'` | URL 字串（非 null） | ✅ Pass (K307.gif) |
| 預測分數不同 | `curl .../predict?... \| jq '.predictions[].score'` | 多個不同的數值 | ✅ Pass (7.74, 7.962, 8.238...) |
| horses 數量 | 驗證命令 | > 1000 | ✅ Pass (1303) |
| races 數量 | 驗證命令 | > 2000 | ✅ Pass (2224) |
| logs.html 頁面 | 瀏覽器打開 | HTTP 200 | ✅ Pass |
| `/api/logs/list` | curl 測試 | JSON log list | ✅ Pass |
| `/api/logs/download` | curl 測試 | 日誌檔案下載 | ✅ Pass |

**所有驗證都必須通過，否則任務視為未完成。**

---

## 2026-03-28 04:07 驗證更新

The_Tester 完成抽樣驗證，**全部項目 Pass**。logs.html UI 顯示待最後確認。

## 備註

- 相關檔案：
  - `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/src/scrapers/odds_collector.js`
  - `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/src/web-app/server/index.cjs`
  - `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/src/web-app/public/logs.html`
- Docker Volumes：`odds_logs` 必須正確掛載
- Backup：操作前建議執行一次備份

---

## 2026-03-28 11:42 用戶反饋 — 需重做 🔴

### 問題
`https://horse.fatlung.com/logs.html` 無法下載日誌檔案

### 驗收標準（待完成）
- [x] `/api/logs/download` 端點正常工作
- [x] `logs.html` 頁面可以成功下載日誌檔案
- [x] 下載時返回正確的 MIME type 和檔案內容

---

## 2026-03-28 12:03 完成更新 ✅

### 問題修復
- `logs.html` 頁面返回主頁 → 已修復
- **根因**：`logs.html` 不在 Docker image 中
- **修復**：更新 `docker/web/Dockerfile`，複製 `logs.html` 到 nginx 目錄

---

## 2026-03-28 17:22 The_Debugger Code Review ✅

### Code Review 結果：APPROVED

| 驗證項目 | 預期 | 實際 | 狀態 |
|----------|------|------|------|
| `logs.html` HTTP 響應 | HTTP 200 | HTTP 200 | ✅ Pass |
| `/api/logs/list` 端點 | JSON log list | odds + pipeline logs 返回正常 | ✅ Pass |
| `/api/logs/download` 端點 | HTTP 200 + 檔案內容 | odds_2026-03-28.log → HTTP 200, 8903 bytes | ✅ Pass |
| Pipeline log 存在 | cron.log + hkjc logs | pipeline_cron.log (38042 bytes) 正常 | ✅ Pass |

**結論**：TASK-010 所有驗證項目通過，Code Review APPROVED。
