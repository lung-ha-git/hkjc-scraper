---
task_id: TASK-012
status: 已驗證
priority: High
assignee: Dev_Alpha
reviewer: The_Debugger
created: 2026-03-29
started: 2026-03-29
completed: 2026-03-29
verified: 2026-03-29
tags:
  - 已驗證
  - Dev_Alpha
  - High
---

# TASK-012: 修復 Scraper `isRaceDay` ReferenceError

## 描述
Odds Collector (hkjc-odds-collector) 在運行時發生 `ReferenceError: Cannot access 'isRaceDay' before initialization` 錯誤，導致所有 race scrape 都返回 ❌。

**錯誤堆疊：**
```
ReferenceError: Cannot access 'isRaceDay' before initialization
    at Timeout.checkRaceDay [_onTimeout] (/app/scrapers/odds_collector.js:369:34)
```

**影響：**
- Scraper 無法正常抓取 odds
- 所有11個 race 都返回 ❌
- 導致 webapp 無法顯示實時 odds

## 根本原因
函數 `isRaceDay` 在 `setInterval` 回調中被調用，但在模塊級別定義之前就被引用了（JavaScript hoisting 問題）。

## 驗收標準
1. ✅ 修復 `isRaceDay` 函數的聲明順序問題
2. ✅ 確保 scraper 在重啟後能正常運行
3. ✅ 所有 11 個 race 都能成功 scrape odds
4. ✅ 驗證 odds 正確寫入 MongoDB

## 交付文件
- `src/scrapers/odds_collector.js`（修復後）

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-03-29 | 建立任務 | The_Brain |

## 審查備註
- 發現人：The_Debugger
- 修復建議：檢查 `isRaceDay` 函數是否在 `setInterval` 回調之前正確聲明，或改用 function declaration 而非 arrow function
