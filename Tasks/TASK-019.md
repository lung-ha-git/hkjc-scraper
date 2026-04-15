# TASK-019: 🐛 Bugfix — Web App 顯示錯誤排位表（World Pool 賽事混入）

## 任務資訊
| 欄位 | 內容 |
|------|------|
| Task | TASK-019 |
| Status | #已驗證 #The_Debugger |
| Priority | #High #URGENT |
| 建立日期 | 2026-04-08 |
| 截止日期 | 2026-04-08（逾期）|
| 指派 | Dev_Alpha |
| started | 2026-04-12 16:39 (HKT) |
| completed | 2026-04-12 17:39 (HKT) |
| verified | 2026-04-12 17:54 (HKT) |

---

## 🔍 問題描述

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

## ✅ 修復方案

### Level 1: Pipeline — 識別並標記 World Pool 賽事
**檔案：** `src/src/crawler/racecard_scraper.py` 或 `save_to_mongodb` 函數

在每個 racecard 文檔中加入：
```json
"race_type": "world_pool"   // 或 "local"
```

識別方式（任選其一）：
1. **API 標記法**：檢查 GraphQL 回傳的 `race_name_en` 或 `race_name_ch` 是否包含 World Pool 相關關鍵字
2. **URL 標記法**：檢查 `racecard_url` 是否包含 `/en-us/local/` → local；`/en-us/racing/information/Racecard.aspx?Racecourse=ST` → local
3. **名稱關鍵字**：若 `race_name_ch` 包含「全球匯合彩池」「海外」「International」→ world_pool

**建議採用 URL 標記法（最準確）**

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

修改 `fetchFixtures`：
```js
// 過濾掉只有 World Pool 的日期
const results = await Promise.all(
  datesToTry.map(d => 
    axios.get(`/api/racecards?date=${d}&include_worldpool=true`).then(r => ({
      date: d, 
      hasLocal: r.data?.racecards?.some(rc => rc.race_type !== 'world_pool')
    })).catch(() => ({ date: d, hasLocal: false }))
  )
);
const match = results.find(r => r.hasLocal);
```

---

## 📋 驗收標準

1. ✅ 本地 HK 賽事（R1-R10）正常顯示
2. ✅ World Pool 海外賽不再顯示（除非用戶主動切換）
3. ✅ 今日（2026-04-08）若無本地賽，自動顯示下一個本地賽日
4. ✅ Pipeline 日後抓取時正確區分 local / world_pool

## Code Review 結果（The_Debugger）
- **審查時間**: 2026-04-12 17:54 (HKT)
- **結果**: ✅ **APPROVED** — 三層修復完整實現

### Level 1 驗證
| 檢查項 | 狀態 |
|--------|------|
| `_detect_race_type()` 函數存在 | ✅ Pass |
| URL 識別邏輯正確 | ✅ Pass |
| 正確標記 `race_type: "world_pool"` | ✅ Pass |

### Level 2 驗證
| 檢查項 | 狀態 |
|--------|------|
| `buildQuery()` 新增 `race_type` 過濾 | ✅ Pass |
| `include_worldpool` 參數處理正確 | ✅ Pass |

### Level 3 驗證
| 檢查項 | 狀態 |
|--------|------|
| `fetchFixtures` 智能跳過邏輯 | ✅ Pass |
| 僅 World Pool 日自動跳轉下一個本地賽日 | ✅ Pass |

## 完成記錄
| 日期 | 更新 |
|------|------|
| 2026-04-12 16:39 | 由 Team Check Cron 創建 TASK-019.md（參考 BUGFIX_overseas_races.md）|
| 2026-04-12 17:39 | Dev_Alpha 完成三層修復：Level 1 (scraper `_detect_race_type`)、Level 2 (API `buildQuery`)、Level 3 (frontend `fetchFixtures`) |
| 2026-04-12 17:54 | The_Debugger Code Review 通過 → 移動至「已驗證」 |
