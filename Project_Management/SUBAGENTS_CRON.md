# Subagents Cron Job 指南

**觸發頻率**: 每 15 分鐘  
**路徑**: `/Users/fatlung/ClawObsidian/Claw/The_Brain`

---

## ⚠️ 嚴禁規則

**禁止刪除 MongoDB Docker Volumes**
- 禁止執行：`docker volume rm`、`docker-compose down --volumes`、`docker volume prune`
- 任何刪除操作必須先獲得用戶書面同意
- 涵蓋：`hkjc_mongodb_data`、`hkjc_api_logs`、`hkjc_models_data`、`hkjc_odds_logs`、`hkjc_pipeline_logs`

---

## 角色職責

### Dev_Alpha 🔧
- **Kanban 職責**: 
  1. 從「需重做」領取任務，執行後移至「已完成」（優先級最高）
  2. 從「待處理」領取任務，執行後移至「已完成」
- **Issue 職責**: 修復 Issue Tracker 中的問題

### The_Debugger 🔍
- **Kanban 職責**: 從「已完成」審查，通過→移至「已驗證」，不通過→移至「需重做」
- **Issue 職責**: 協助 Debug Issue、Code Review

### The_Tester 🧪
- **Kanban 職責**: 從「已驗證」制定測試計畫
- **Issue 職責**: 發現問題→記錄到 Issue_Tracker，指派給 Dev_Alpha 或 The_Debugger

---

## 檔案路徑（絕對路徑）

| 檔案 | 路徑 |
|------|------|
| Kanban | `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/Project_Management/Kanban.md` |
| Issue Tracker | `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/Project_Management/Issue_Tracker.md` |
| 指南 | `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/Project_Management/SUBAGENTS_CRON.md` |
| Team Check 日誌 | `/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/Logs/team_check_YYYYMMDD.md` |

---

## 日誌記錄 ⚠️

每次 Check 完成後，**必須**將 output 寫入日誌檔案：

```
/Users/fatlung/ClawObsidian/Claw/The_Brain/Logs/team_check_YYYYMMDD.md
```

**時間逆順：新內容在最頂端，舊內容往下推。**

**方法：讀取現有內容，然後用新內容 + 舊內容寫入同一檔案。**

```bash
# 讀取舊內容（如果存在的話）
OLD_CONTENT=""
if [ -f "$LOG_FILE" ]; then
  OLD_CONTENT=$(cat "$LOG_FILE")
fi

# 生成新內容（包含時間戳和檢查結果）
NEW_CONTENT="=== [$(date +%H:%M)] Team Check ===
[角色] 檢查結果：
- 發現任務：...
- 執行操作：...
- 狀態更新：...

$OLD_CONTENT"

# 寫入（覆蓋模式，因為我們已經讀取了舊內容）
echo -e "$NEW_CONTENT" > "$LOG_FILE"
```

**重要：不要覆蓋檔案，必須保留舊內容並放在新內容下方。**

---

## Cron Job 觸發流程

```
1. 讀取 SUBAGENTS_CRON.md 了解角色職責
2. 檢查 Kanban 對應欄位
3. 檢查 Issue Tracker 待處理 Issue
4. 執行職責並更新狀態
5. 回報「No tasks pending」（如適用）
```

---

## Issue 處理流程

| Issue 狀態 | 負責人 | 行動 |
|------------|--------|------|
| 🔴 待修復 | Dev_Alpha | 修復並回報 |
| ⚠️ 待驗證 | The_Tester | 驗證修復結果 |
| ✅ 已修復 | The_Tester | 更新為已關閉 |

---

## 重要規則

### 搶單規則 ⚠️
- **有指定成員標籤的任務不可搶單**
  - 如：任務有 `#Dev_Alpha` 標籤 → 只有 Dev_Alpha 可領取
  - 如：任務有 `#The_Debugger` 標籤 → 只有 The_Debugger 可領取
  - 如：任務有 `#The_Tester` 標籤 → 只有 The_Tester 可領取
- **沒有標籤的任務** → 任何人可搶單
- 領取後**立即**更新為「#進行中」
- 不得出現「有人領取但狀態仍是待處理」

### 狀態更新
- Task 文件 + Kanban.md **同步更新**
- Issue Tracker 狀態欄位**即時更新**

---

*最後更新：2026-03-27*
