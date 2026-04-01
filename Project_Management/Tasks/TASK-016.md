---
task_id: TASK-016
status: 已完成
priority: Medium
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

# TASK-016: 移除 WebSocket 連線時長顯示 `📡 上午：08:10...`

## 描述
Webapp 桌面版 `race-info` 區域顯示了 `📡 上午：08:10 – ...`，這是 WebSocket 連線啟動時間，對用戶沒有實際意義且格式怪異。

**目前代碼（App.jsx ~320 行）：**
```jsx
{session?.started_at && (
  <span className="odds-service-time">
    📡 {fmtTime(session.started_at)}{session.finished_at ? ` – ${fmtTime(session.finished_at)}` : ' – ...'}
  </span>
)}
```

**修復方案：**
直接刪除這段 JSX。連線狀態指示燈由 TASK-018 統一處理，這裡只做移除。

## 驗收標準
1. 桌面版 `race-info` 不再顯示 `📡 上午：08:10...` 時間文字
2. 不增加任何替代顯示（連線燈由 TASK-018 處理）

## 交付文件
- `Projects/HKJC/src/web-app/src/App.jsx` — 移除 `session?.started_at` 顯示，改為連線指示燈

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-04-01 | Task 建立 | The_Brain |

## 審查備註
