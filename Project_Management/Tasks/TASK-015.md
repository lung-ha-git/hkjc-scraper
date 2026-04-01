---
task_id: TASK-015
status: 已完成
priority: High
assignee: Dev_Alpha
reviewer: The_Debugger
created: 2026-04-01
started: 
completed: 2026-04-01 
verified: 
tags:
  - 待處理
  - Dev_Alpha
---

# TASK-015: Webapp 顯示跑道資料

## 描述
在 Webapp UI 中增加跑道資訊顯示。目前 UI 只顯示「沙田/跑馬地」的中文名稱，但缺少更具體的跑道資料（如跑道編號、跑道狀況說明等）。

**需求分析：**
- 目前 `currentRaceCards` 包含 `track_code`、`track_condition` 等欄位
- 需在桌面版 `race-header` 和手機版 `ut-mobile-header` 區域增加跑道資訊顯示

## 驗收標準
1. 桌面版：第 N 場資訊列顯示跑道代碼（如「A+3 / 好地」）
2. 手機版：Race Header 顯示跑道代碼
3. 若無跑道資料則顯示「-」

## 交付文件
- `Projects/HKJC/src/web-app/src/App.jsx` — 修改 `race-header` 和 `ut-mobile-header` 區域
- 修改後截圖對比

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-04-01 | Task 建立 | The_Brain |

## 審查備註
