---
task_id: TASK-019
status: 待處理
priority: High
assignee: Dev_Alpha
reviewer: The_Debugger
created: 2026-04-08
started: 
completed: 
verified: 
tags:
  - 待處理
  - Dev_Alpha
---

# TASK-019: 🐛 Bugfix — Web App 顯示錯誤排位表（World Pool 賽事混入）

## 優先級：URGENT 🔴
## 日期：2026-04-08
## ⚠️ 逾期：今天（2026-04-12）仍未列入 Kanban

---

## 問題描述

用戶反映 web app 顯示了錯誤的排位表，**顯示海外 World Pool 賽事而非本地香港賽事**。

### 根本原因
1. `2026-04-08` 這天**沒有本地 HK 賽事**，只有 World Pool 國際賽（8 場全是海外賽）
2. Pipeline 把 World Pool 賽事錯誤地存入了 `racecards` collection，venue = 'ST'
3. API `/api/racecards` 回傳所有賽事（包含 World Pool），沒有過濾
4. 前端 `fetchFixtures` 預設取第一個有資料的 fixture date

### World Pool 賽事名稱（2026-04-08）
- R1: 主席讓賽（Group 2 海外）
- R2: 香港賽馬會全球匯合彩池卡賓會錦標
- R3: 鄉郊錦標決賽（澳洲）
- R4: 澳洲賽馬會育馬錦標
- R5: 史密夫錦標（澳洲）
- R6: 唐加士打一哩賽
- R7: 澳洲打吡
- R8: 貝堯錦標

---

## 修復方案

### Level 1: Pipeline — 識別並標記 World Pool 賽事
**檔案：** `src/src/crawler/racecard_scraper.py` 或 `save_to_mongodb` 函數

在每個 racecard 文檔中加入：
```json
"race_type": "world_pool"   // 或 "local"
```

識別方式（URL 標記法）：
- 檢查 `racecard_url` 是否包含 `/en-us/local/` → local
- 檢查 `racecard_url` 是否包含 `/en-us/racing/information/Racecard.aspx?Racecourse=ST` → local
- 或名稱關鍵字：若 `race_name_ch` 包含「全球匯合彩池」「海外」「International」→ world_pool

### Level 2: API — 過濾 World Pool
**檔案：** `src/web-app/server/index.cjs`

修改 `/api/racecards`：
```js
app.get('/api/racecards', async (req, res) => {
  // ...
  let query = { race_date: date };
  if (venue) query.venue = venue;
  // 新增：過濾掉 World Pool
  if (!req.query.include_worldpool) {
    query.race_type = { $ne: 'world_pool' };
  }
  // ...
});
```

### Level 3: 前端 — 智能跳過 World Pool 日
**檔案：** `src/web-app/src/App.jsx`

修改 `fetchFixtures`：過濾掉只有 World Pool 的日期，自動顯示下一個本地賽日

---

## 驗收標準

1. ✅ 本地 HK 賽事（R1-R10）正常顯示
2. ✅ World Pool 海外賽不再顯示（除非用戶主動切換）
3. ✅ 今日（2026-04-08）若無本地賽，自動顯示下一個本地賽日
4. ✅ Pipeline 日後抓取時正確區分 local / world_pool

---

## ⚠️ 狀態更新規則

每次移動 Task，**必須同時做兩件事**：
1. `status:` 欄位改為新狀態
2. `tags:` 陣列**加入狀態標籤**（`#待處理` / `#進行中` / `#已完成` / `#已驗證` / `#需重做`）
3. 同步更新 `Kanban.md` 中的 Task 引用，**必須包含狀態標籤**

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-04-12 16:24 | 從 BUGFIX_overseas_races.md 升級為正式 TASK-019，加入 Kanban 待處理 | The_Brain |

## 審查備註
URGENT 🔴：原檔案創建於 2026-04-08，已逾期 4 天仍未修復。盡快處理。

---

## Issue #IT-011：Pipeline 跳過重抓導致 `race_type` 從未設定（2026-04-13）

### 根本原因
`daily_pipeline.py` 的 `_scrape_racecards()` 邏輯：
```python
existing = db.db["racecards"].count_documents({...})
if existing > 0:
    return  # ← 跳過重抓
```
結果：04-12 的 World Pool 數據在 04-03 已存在，Pipeline 從未重新抓取，因此 `race_type` 欄位從未被設定。

### 修復措施
1. **緊急修復（已完成）**：MongoDB 遷移腳本，一次過設定所有歷史數據的 `race_type`
   - 157 條記錄 → 142 local + 15 world_pool ✅
2. **代碼修復（已完成）**：更新 `_WP_KEYWORDS`（+ 12 個關鍵字）
3. **Git 提交**：✅ 已推送（commit 30e7873）

### 待跟進任務
| 優先級 | 行動 | 負責人 |
|--------|------|--------|
| 🔴 High | Pipeline 添加 `--force-racecards` 參數，強制重抓現有數據 | Dev_Alpha |
| 🔴 High | Rebuild + 重部署 API/Web/Pipeline 容器 | Dev_Alpha |
| 🟡 Medium | 重抓 2026-05-06、2026-05-09 的 World Pool 數據（確保 URL 準確）| Dev_Alpha |

### 數據庫遷移記錄
```js
// 2026-04-13 完成
// 影響：157 條 racecards，0 條 missing
// World Pool dates: 2026-04-04, 2026-04-06, 2026-04-08, 2026-04-12, 2026-04-15, 2026-05-06, 2026-05-09
```
