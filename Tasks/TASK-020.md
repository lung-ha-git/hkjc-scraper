# TASK-020: Pipeline 添加 --force-racecards 參數

## 任務資訊
| 欄位 | 內容 |
|------|------|
| Task | TASK-020 |
| Status | #待處理 #Dev_Alpha |
| Priority | #High |
| 建立日期 | 2026-04-13 |
| 指派 | Dev_Alpha |

---

## 背景

TASK-019 修復中發現：Pipeline 的 `_scrape_racecards()` 跳過已有 racecards 的日期，導致 scraper 邏輯更新後歷史數據不會被重新標記。

## 修復方向

在 `daily_pipeline.py` 的 PART 1 中新增 `--force-racecards` CLI 參數：
```python
# 當指定 --force-racecards 時，忽略 existing > 0 檢查，強制重抓
if args.force_racecards:
    logger.info("   🔄 --force-racecards: 強制重抓")
else:
    if existing > 0:
        return  # 現有邏輯
```

## 驗收標準
1. `--force-racecards` 參數存在且生效
2. 強制重抓不產生重複記錄（`race_id` 唯一鍵）
3. 日誌清楚顯示「強制重抓」區分一般跳過

## Code Review
由 The_Debugger 負責

## 歷史記錄
| 日期 | 更新 |
|------|------|
| 2026-04-13 | 由 The_Brain 建立（預防日後重蹈 TASK-019 問題）|
