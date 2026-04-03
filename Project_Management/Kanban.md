---
kanban_plugin: '{"columns":["待處理","進行中","已完成","已驗證","需重做"],"scope":"folder","showFilepath":true,"consolidateTags":false,"uncategorizedVisibility":"auto","doneVisibility":"always","doneStatusMarkers":"xX","cancelledStatusMarkers":"-","ignoredStatusMarkers":"","savedFilters":[],"lastContentFilter":"","lastTagFilter":[],"lastFileFilter":[],"columnWidth":300,"flowDirection":"ltr","collapsedColumns":[],"defaultTaskFile":"","lastUsedTaskFile":"","scopeFolders":[],"excludePaths":[]}'
---
## 待處理

（無）

## 進行中

（無）

## 已完成

（無）

## 已驗證

- [x] [[TASK-015|TASK-015: Webapp 顯示跑道資料]] #已驗證 #The_Debugger #Dev_Alpha #High
- [x] [[TASK-016|TASK-016: 修復 Webapp 不明時間格式 `上午：08:10...`]] #已驗證 #The_Debugger #Dev_Alpha #Medium
- [x] [[TASK-017|TASK-017: Webapp 增加開跑時間（從 WebSocket 獲取）]] #已驗證 #The_Debugger #Dev_Alpha #High
- [x] [[TASK-018|TASK-018: Webapp 增加賠率更新時間]] #已驗證 #The_Debugger #Dev_Alpha #Medium
- [x] [[TASK-010|TASK-010: Odds Collector Log 重新實作 + 驗證完整功能]] #已驗證 #The_Debugger #High
- [x] [[TASK-012|TASK-012: 修復 Scraper `isRaceDay` ReferenceError]] #已驗證 #Dev_Alpha #High
- [x] [[TASK-013|TASK-013: API Server 啟動時預加載 Odds Cache]] #已驗證 #Dev_Alpha #High
- [x] [[TASK-014|TASK-014: API Server 預加載 Odds Cache（預防重啟後失效）]] #已驗證 #Dev_Alpha #High

- [x] [[TASK-011|TASK-011: Pipeline Cron Job 未運行調查 + MongoDB_URI 修復驗證]] #已驗證 #The_Debugger #High
- [x] [[TASK-009|TASK-009: Team Check Cron Log Accumulation]] #已驗證 #Dev_Alpha #Medium
- [x] [[TASK-008|TASK-008: 將 odds-collector service 加入 Docker 環境]] #已驗證 #The_Brain #High
- [x] [[TASK-007|TASK-007: 修復 predict API Feature Mismatch (19→29 features)]] #已驗證 #The_Debugger #High
- [x] [[TASK-006|TASK-006: 修復 sync_past_race_results 查詢錯誤]] #已驗證 #The_Debugger #High
- [x] [[TASK-003|TASK-003: 撰寫 Docker 安裝與起始文檔]] #已驗證 #The_Tester #High
- [x] [[TASK-001|TASK-001: 製作 Feature Document & Technical Guide]] #已驗證 #Dev_Alpha #Medium
- [x] [[TASK-002|TASK-002: Docker 化 HKJC 專案]] #已驗證 #Dev_Alpha #High
- [x] [[TASK-005|TASK-005: 設定 Cloudflare Tunnel (horse.fatlung.com)]] #已驗證 #Dev_Alpha #High

## 需重做

（無）

---

## 📋 工作流程說明

### 創建新任務
1. 在 `Tasks/` 文件夾創建 `TASK-XXX.md`
2. 使用 [[Task_Template]] 模板
3. 設置 `status: 待處理`
4. 在 Kanban 對應欄位添加引用：`[[TASK-XXX]] #待處理`

### 欄位轉移流程
| 轉移 | 執行人 | 操作 |
|------|--------|------|
| **待處理 → 進行中** | **搶單者（任何人）** | **誰領取任務，誰即時更新 Task 文件 `status: 進行中`，Kanban 標籤改為 `#進行中`（包含 `#<成員>` 標籤表明負責人）** |
| 進行中 → 已完成 | Dev_Alpha / The_Tester | Task 文件 `status: 已完成`，Kanban 標籤改為 `#已完成` |
| 已完成 → 已驗證 | The_Debugger | Task 文件 `status: 已驗證`，Kanban 標籤改為 `#已驗證` |
| 已完成 → 需重做 | The_Debugger | Task 文件 `status: 需重做`，Kanban 標籤改為 `#需重做` |
| 需重做 → 進行中 | Dev_Alpha / The_Tester | Task 文件 `status: 進行中`，Kanban 標籤改為 `#進行中` |

> **⚠️ 重要規則：任何人員領取 `#待處理` 任務後，必須立即更新狀態為 `#進行中`，不得出現「有人領取但狀態仍是待處理」的情況。**

### Dev_Alpha 提醒
參見 [[Dev_Alpha 工作流程指南]]

## ⚠️ 任務創建規則

**創建新 Task 時，必須同時指派負責人：**
- `assignee:` 填寫實際負責人（Dev_Alpha / The_Debugger / The_Tester）
- `tags:` 加上對應成員標籤（`#Dev_Alpha` / `#The_Debugger` / `#The_Tester`）
- 不允許建立「沒有人負責」的待處理任務

## ⚠️ 狀態更新規則

**每次 Task 狀態改變時，必須同時滿足以下兩件事：**

1. **Task 文件更新**
   - `status:` 欄位改為新狀態
   - `completed:` / `verified:` / `started:` 等時間欄位填寫
   - `tags:` **必須包含狀態標籤**（`#待處理` / `#進行中` / `#已完成` / `#已驗證` / `#需重做`）

2. **Kanban.md 更新**
   - 將 Task 引用移動到對應欄位
   - **必須加上狀態標籤**，例如：`[[TASK-015|TASK-015: ...]] #已完成 #Dev_Alpha`

**⚠️ 錯誤範例（狀態標籤缺失）：**
```
- [ ] [[TASK-XXX|TASK-XXX: 任務標題]] #Dev_Alpha  ← ❌ 缺 #進行中
```

**✅ 正確範例：**
```
- [ ] [[TASK-XXX|TASK-XXX: 任務標題]] #待處理 #Dev_Alpha
- [ ] [[TASK-XXX|TASK-XXX: 任務標題]] #進行中 #Dev_Alpha
- [ ] [[TASK-XXX|TASK-XXX: 任務標題]] #已完成 #Dev_Alpha
```



**狀態標籤**（決定 Kanban 欄位）：
- `#待處理`, `#進行中`, `#已完成`, `#已驗證`, `#需重做`

**團隊標籤**：
- `#Dev_Alpha`, `#The_Debugger`, `#The_Tester`

**優先級標籤**：
- `#High`, `#Medium`, `#Low`
































































