# TASK-006: 修復 sync_past_race_results 查詢錯誤

**創建日期**: 2026-03-27  
**狀態**: 已完成  
**執行人**: Dev_Alpha  
**優先級**: High

---

## 問題描述

`sync_past_race_results()` 查詢 `fixtures` collection，但過去的賽事數據存儲在 `races` collection。

### 當前行爲
```python
# 查詢 fixtures - 只有未來的賽事
fixtures = list(db.db["fixtures"].find({
    "race_date": {"$gte": start_date, "$lt": today.strftime("%Y-%m-%d")}
}))
```

### 正確行爲
應該查詢 `races` collection 中的 `race_date` 欄位

## 修復步驟

修改 `src/src/pipeline/history.py` 中的 `sync_past_race_results()` 函數：

1. 從 `races` collection 查詢過去的賽事日期
2. 或者從 `races` collection 查詢，然後對比 `fixtures` 找出缺失的

## 驗證

修復後運行：
```bash
docker exec hkjc-pipeline python3 daily_pipeline.py --part 2 --days-back 60
```

應該能檢測並同步缺失的歷史數據。
