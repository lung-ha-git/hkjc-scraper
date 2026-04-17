# n8n 本地版遷移評估 — 2026-04-17

## 評估時間
- 日期：2026-04-17 13:12 HKT
- 評估者：The_Brain

---

## 評估背景
用戶詢問是否可以在 Mac mini 上安裝 n8n 本地版，並將 HKJC Pipeline 和 Odds Collector 遷移到 n8n。

---

## 現有系統組件

| 組件 | 語言 | 運行頻率 | 代碼行數 |
|------|------|----------|----------|
| `daily_pipeline.py` | Python | 每日 06:00 | 1014 行 |
| `odds_collector.js` | Node.js | 賽日每 5 秒 | 長駐進程 |

---

## n8n 本地版安裝

### 安裝方式（Docker）
```bash
docker volume create n8n_data
docker run -d \
  --name n8n \
  --restart unless-stopped \
  -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n
```

**安裝複雜度：⭐⭐（簡單）**
- 已有 Docker 環境，無需額外依賴
- 預設使用 SQLite，無需 PostgreSQL

---

## 遷移可行性評估

### daily_pipeline.py → n8n Workflow

| 功能 | n8n 支援程度 |
|------|-------------|
| Cron Schedule (`0 6 * * *`) | ✅ 完整支援 |
| Python 執行 | ⚠️ 需 Execute Command Node |
| MongoDB 讀寫 | ✅ 原生支援 |
| ML 模型訓練 | ❌ 無法直接支援 |
| Git Push | ⚠️ 需 Execute Command |

**結論**：可以遷移，但收益有限。n8n 只是包了一層 trigger + 通知，Python 邏輯完全無法遷移。

### odds_collector.js → n8n Workflow

| 功能 | n8n 支援程度 |
|------|-------------|
| 每 5 秒抓取 | ❌ **不可能**（n8n cron 最小精度 1 分鐘）|
| 賽日/非賽日智能判斷 | ❌ 無法原生實現 |
| 連續運行 12+ 小時 | ❌ 不適合長駐進程 |
| 內存狀態管理 | ❌ 無法跨執行保留 |

**結論**：❌ **不建議遷移** — 核心價值在於 5 秒級別即時性和長駐進程，n8n 無法支援。

---

## 優缺點分析

### ✅ 優點
- 視覺化監控（實時看到每個步驟的執行狀態）
- 內置告警系統（Pipeline 失敗時自動 Discord/Email 通知）
- 執行歷史記錄
- Webhook 觸發能力
- 團隊協作

### ❌ 缺點
- 額外服務維護
- odds_collector 的 5 秒抓取不可能實現
- Python ML 訓練邏輯搬不過去
- 學習成本
- 資源佔用

---

## 推薦方案

### 方案 A：完全不遷移（維持現狀）⭐⭐⭐⭐⭐

**理由：**
- `daily_pipeline.py` 現有架構簡潔高效
- `odds_collector.js` 根本不可能遷移到 n8n
- 唯一的痛點是「監控日誌」，可通過其他方式解決

### 方案 B：n8n 只用於「監控 + 告警」⭐⭐⭐

```
n8n Workflow:
  [Cron: 每小時]
    → [Execute: docker exec hkjc-pipeline tail -5 pipeline_cron.log]
    → [IF error found] → [Discord Alert]
```

**只解決告警問題，不遷移核心邏輯。**

### 方案 C：完整遷移到 n8n ⭐

**不推薦** — 用更複雜的架構做同樣的事。

---

## 替代方案（不需 n8n）

1. **加強 Cron Job 告警** — 在 pipeline_cron.log 尾部加成功/失敗標記
2. **OpenClaw Cron Job 通知** — 現有的 Team Check 已經每 15 分鐘檢查一次
3. **日誌聚合** — 把 pipeline logs 統一到一個可視化 dashboard

---

## 結論

**維持現狀，不遷移到 n8n。**

原因：
1. odds_collector 的核心價值（5 秒抓取 + 長駐進程）無法遷移
2. daily_pipeline 的 Python 邏輯無法遷移
3. 現有 OpenClaw 團隊檢查機制已足夠

如果需要更好的監控，優先考慮方案 B（n8n 只做告警），而非完整遷移。
