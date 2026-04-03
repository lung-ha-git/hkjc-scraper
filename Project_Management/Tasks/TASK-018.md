---
task_id: TASK-018
status: 已完成
priority: Medium
assignee: Dev_Alpha
reviewer: The_Debugger
created: 2026-04-01
started: 
completed: 2026-04-01 
verified: 
tags:
  - 已完成
  - Dev_Alpha
verified: 2026-04-01
reviewer_notes: |
  ✅ 驗收標準 1-4 全部滿足：桌面顯示精確秒數、綠/紅連線燈、手機同步、2分鐘警告
  ✅ 斷線處理完善，超時提示清晰
  → 移至「已驗證」
---

# TASK-018: Webapp 增加賠率更新時間

## 描述
在 Webapp 中增加「賠率最後更新時間」顯示，讓用戶知道Odds數據的新鮮程度。

**需求分析：**
- WebSocket 每筆 `odds_update` 包含 `timestamp`
- `oddsData[horse_no]` 包含 `updated_at` 欄位（來自 `useOddsSocket` hook）
- 可顯示：整場的最後更新時間 + 每匹馬的更新時間
- WebSocket 連線狀態由 `connected` boolean 表示

**設計方案：**
1. 在桌面版 `race-header` 右側增加「📡 最後更新: 14:32:05」
2. 可在每匹馬的 WIN/PLA 數值旁增加小標示（如 tooltip 或 hover）
3. 當 WebSocket 斷線時（`connected === false`），顯示離線提示
4. 手機版：同樣位置顯示「📡 14:32」

## 驗收標準
1. 桌面版顯示最後更新時間（精確到秒）
2. WebSocket 連線時顯示綠色連線標示；斷線時顯示紅色「❌ 離線」
3. 手機版同步顯示（可縮短格式）
4. 若超過 2 分鐘無更新，顯示「⚠️ 更新延遲」

## 交付文件
- `Projects/HKJC/src/web-app/src/App.jsx` — 增加連線狀態和更新時間顯示
- `Projects/HKJC/src/web-app/src/index.css` — 如需新增樣式

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-04-01 | Task 建立 | The_Brain |

## 審查備註
