---
task_id: TASK-XXX
status: 待處理
priority: Medium
assignee: 
reviewer: 
created: 
started: 
completed: 
verified: 
tags:
  - 待處理
---

# TASK-XXX: {任務標題}

## 描述
{任務描述}

## 驗收標準

## 交付文件
- {文件路徑}

## ⚠️ 狀態更新時必須同時更新標籤

每次移動 Task，**必須同時做兩件事**：
1. `status:` 欄位改為新狀態
2. `tags:` 陣列**加入狀態標籤**（`#待處理` / `#進行中` / `#已完成` / `#已驗證` / `#需重做`）
3. 同步更新 `Kanban.md` 中的 Task 引用，**必須包含狀態標籤**

正確：`tags: [待處理, Dev_Alpha]`
正確：`tags: [進行中, Dev_Alpha]`

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| | | |

## 審查備註
{審查意見}
