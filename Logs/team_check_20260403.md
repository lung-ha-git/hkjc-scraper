# HKJC 進度記錄 — 2026-04-03

## 🔧 Pipeline Cron 緊急修復

### 問題 1：Cron Job 未運行（4/1–4/3 連續 2 天）
- **根因**：User Crontab 用 `python3`（無完整路徑），cron 執行時找不到 binary
- **修復**：更新 crontab 為 `/usr/local/bin/python3`
- **驗證**：✅ 手動觸發成功，Cron 明天 6:00 自動運行

### 問題 2：`pipeline_*.log` 為空（logging 失效）
- **根因**：`daily_pipeline.py` 的 `basicConfig(FileHandler)` 在 imports 之後執行，但被 import 的 modules（如 `fixtures.py`）在 import 時搶先執行 `logging.basicConfig(level=INFO)`，導致 `basicConfig` 變成 no-op，所有 log 只去 stdout
- **修復**：
  1. `basicConfig` 後強行 `setFormatter()` 到所有已存在的 handlers
  2. 確保 `FileHandler` 存在
- **驗證**：✅ `pipeline_20260403.log` 正常寫入，時間戳完整

### 問題 3：GraphQL 返回錯誤賽日（排位表抓到別的日期數據）
- **根因**：`handle_route` 被動接收頁面 JS 的 GraphQL request，未控制 `variables.date`，API 返回「下一場賽事」而非指定日期
- **修復**：
  1. 攔截並 `abort` 原始 raceMeetings 請求
  2. 用 `page.evaluate()` + `fetch()` 重新發送，正確傳入 `variables: {date, venueCode}`
- **驗證**：✅ April 6 正確返回 `MTG_20260406_0001`，11 場、138 匹馬

### 問題 4：logs.html 看不到 pipeline log
- **根因**：API `PIPELINE_LOGS_DIR` 指向 `/app/logs/pipeline/`，但 pipeline 寫入 `/app/logs/pipeline/pipeline/`
- **修復**：API 端改為 `/app/logs/pipeline/pipeline`
- **驗證**：✅ logs.html 顯示 `pipeline_20260403.log: 8151B`

### 附加修復
- `racecards.py`：爬完後同步更新 `fixture.race_count`
- 清理錯誤的 April 6/8/12/15/19/22 racecards，手動重爬 April 6 ✅
- 追蹤 `src/src/` 目錄（從 .gitignore 移除，共 71 files）

## 📊 當前數據狀態
| 日期 | 狀態 | 場次 |
|------|------|------|
| 2026-04-06 (ST) | ✅ completed | 11 場 |
| 2026-04-08 (ST) | ⏳ pending | 2 場 |
| 2026-04-12 (ST) | ⏳ pending | 2 場 |
| 2026-04-15 (ST) | ⏳ pending | 2 場 |
| 2026-04-19 (ST) | ⏳ pending | 1 場 |

## Git Commit
- `71e403d` fix(pipeline): 修復 pipeline cron 三大問題
