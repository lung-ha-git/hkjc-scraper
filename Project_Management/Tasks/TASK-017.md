---
task_id: TASK-017
status: 已測試
priority: High
assignee: Dev_Alpha
reviewer: The_Debugger
tester: The_Tester
created: 2026-04-01
started: 
completed: 2026-04-01 
verified: 2026-04-01
tested: 2026-04-03
tags:
  - 已測試
  - Dev_Alpha
  - The_Tester
verified: 2026-04-01
reviewer_notes: |
  ✅ 驗收標準 1-4 全部滿足：桌面/手機顯示、格式統一「⏱ 14:30」、臨近高亮
  ✅ 利用現有 /api/racecards 的 race_time，無需新增 API
  → 移至「已驗證」
tester_notes: |
  ✅ 靜態審查 S-01~S-07 全部 Pass
  ✅ raceTimeStr 正確格式化 post_time (HH:MM)
  ✅ isRaceTimeNear 正確判斷 < 5 分鐘臨近
  ✅ API 驗證 post_time: "2026-03-29T12:45:00+08:00" 存在
  ✅ Desktop/Mobile 兩處皆有顯示
---

# TASK-017: Webapp 增加開跑時間（從 WebSocket 獲取）

## 描述
在 Webapp 中增加「開跑時間」顯示。開跑時間應從 WebSocket 即時獲取，而非僅依賴頁面加載時的靜態資料。

**需求分析：**
- `racecards` collection 中每場比賽有 `race_time`（開跑時間）
- WebSocket `useOddsSocket` hook 的 `session` 包含 `started_at`（僅為 WebSocket 連線時間，非開跑時間）
- 需新增 API endpoint 或利用現有 `racecards` API 回傳的 `race_time`
- 在桌面版和手機版 UI 中均顯示開跑時間

**設計方案：**
1. `GET /api/racecards` 已包含 `race_time` → 直接使用
2. 若 WebSocket 推送了即時開跑時間，則使用實時值覆蓋
3. 顯示格式：`開跑 14:30` 或 `⏱ 14:30`

## 驗收標準
1. 桌面版和手機版皆顯示「開跑時間」
2. 若無開跑時間（如賽前太早）顯示「-」
3. 格式統一：`⏱ 14:30`
4. 臨近開跑時（如 < 5 分鐘）高亮或變色提示

## 交付文件
- `Projects/HKJC/src/web-app/src/App.jsx` — 增加開跑時間顯示
- 如需要：`Projects/HKJC/src/web-app/server/index.cjs` — 新增/修改 API

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-04-01 | Task 建立 | The_Brain |

## 審查備註
