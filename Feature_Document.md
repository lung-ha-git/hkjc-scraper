# HKJC AI 預測系統 - Feature Document

## 文件資訊
- **版本**: v1.0
- **作者**: Dev_Alpha
- **日期**: 2026-03-26
- **狀態**: 進行中 (TASK-001)

---

## 📋 功能概覽

本系統為香港賽馬會 (HKJC) 賽事提供 AI 驅動的預測分析，整合實時賠率、歷史數據和機器學習模型。

---

## 功能一：實時賠率收集與 WebSocket 推送

### 1.1 功能描述
自動從 HKJC 官方網站抓取實時賠率數據，並通過 WebSocket 推送到前端界面。

### 1.2 核心組件

| 組件 | 路徑 | 說明 |
|------|------|------|
| Odds Collector | `scrapers/odds_collector.js` | 使用 Playwright 爬取賠率 |
| WebSocket Hook | `web-app/src/hooks/useOddsSocket.js` | 前端 WebSocket 連接 |
| API Server | `server.js` (port 3001) | Socket.IO 服務端 |

### 1.3 技術實現

#### 數據抓取流程
```javascript
// 每個週期啟動全新 Chrome 實例（避免 rate-limit）
browser → page.goto(HKJC_URL) → intercept GraphQL response → parse odds
```

**GraphQL 攔截點**: `info.cld.hkjc.com/graphql`
**數據欄位**: `pmPools` → `oddsNodes` → `oddsValue`

#### WebSocket 事件
| 事件名稱 | 方向 | 數據格式 |
|----------|------|----------|
| `subscribe` | Client → Server | `{ race_id: "2026-03-22_ST_R7" }` |
| `odds_update` | Server → Client | `{ horse_no, win, place, timestamp }` |
| `odds_snapshot` | Server → Client | `{ odds: {}, session: {} }` |
| `odds_session_end` | Server → Client | `{ session: { started_at, finished_at } }` |

### 1.4 數據存儲
- **MongoDB Collection**: `live_odds`
- **保留策略**: 所有歷史賠率記錄
- **索引**: `race_id`, `scraped_at`

### 1.5 UI 展示
- 桌面端：Sparkline 圖表顯示賠率走勢
- 移動端：當前賠率數值 + 走勢指示

---

## 功能二：AI 預測與因子調整

### 2.1 功能描述
基於 XGBoost 模型的賽事預測系統，支持用戶調整不同因子權重來影響預測結果。

### 2.2 模型配置

```json
// config/model-config.json
{
  "models": {
    "xgb-default": {
      "features": 23,
      "accuracy": 0.567,
      "status": "active",
      "default": true
    },
    "xgb-enhanced": {
      "features": 36,
      "accuracy": 0.60,
      "status": "development"
    },
    "ensemble": {
      "features": 36,
      "accuracy": 0.62,
      "status": "planned"
    }
  }
}
```

### 2.3 可調整因子 (Boosting)

| 因子鍵 | 中文名稱 | 默認值 | 範圍 | 說明 |
|--------|----------|--------|------|------|
| `distance` | 路程成績 | 1.0 | 0-3x | 馬匹在特定路程的歷史表現 |
| `jockey` | 騎師/組合 | 1.0 | 0-3x | 騎師與馬匹組合勝率 |
| `recent` | 近績 | 1.0 | 0-3x | 最近 10 場表現 |
| `track` | 跑道/狀況 | 1.0 | 0-3x | 跑道類型和狀況適應性 |
| `draw` | 檔位 | 1.0 | 0-3x | 起跑檔位優劣 |
| `career` | 歷史戰績 | 1.0 | 0-3x | 生涯勝率統計 |
| `trainer` | 練馬師 | 1.0 | 0-3x | 練馬師本季表現 |
| `best_time` | 最快時間 | 1.0 | 0-3x | 同路程最佳完賽時間 |
| `pace` | 前中後段速 | 1.0 | 0-3x | 步速分析 |

### 2.4 API 端點
```
GET /api/predict?race_date={date}&race_no={no}&venue={venue}&boosting={json}
```

### 2.5 信心指數 (Confidence Score)
- **計算方式**: 基於模型輸出概率分佈
- **顯示**: 0-100 數值
- **顏色標識**: 
  - 🟢 > 65: 高信心
  - 🟡 55-65: 中等
  - 🔴 < 55: 低信心

---

## 功能三：賽事數據管理與排位表

### 3.1 功能描述
管理賽事日程、排位表、馬匹資料等核心數據，支持 Web 界面查看。

### 3.2 數據模型

#### Race (賽事)
| 欄位 | 類型 | 說明 |
|------|------|------|
| `hkjc_race_id` | String | 唯一標識，如 `2026_03_15_ST_1` |
| `race_date` | Date | 賽事日期 |
| `venue` | String | ST (沙田) / HV (跑馬地) |
| `race_no` | Number | 場次編號 |
| `distance` | String | 路程，如 `1000米` |
| `class` | String | 班次，如 `五班` |
| `track_condition` | String | 場地狀況 |
| `entries` | Array | 參賽馬匹列表 |
| `results` | Array | 賽事結果 |
| `payout` | Object | 派彩數據 |

#### Horse (馬匹)
| 欄位 | 類型 | 說明 |
|------|------|------|
| `hkjc_horse_id` | String | 唯一標識，如 `HK_2025_L108` |
| `horse_code` | String | 馬號，如 `L108` |
| `name` | String | 馬名 |
| `jersey_url` | String | 彩衣圖片 URL |
| `current_rating` | Number | 現有評分 |
| `career_wins` | Number | 生涯頭馬數 |
| `trainer` | String | 練馬師 |

#### Jockey (騎師) & Trainer (練馬師)
統計數據包括：頭馬數、亞軍、季軍、總出賽次數、獎金等

### 3.3 API 端點
```
GET /api/fixtures              # 獲取賽事日程
GET /api/racecards?date={date} # 獲取指定日期排位表
GET /api/validations/{date}/{venue} # 驗證數據變更
```

### 3.4 UI 組件
- **Race Tabs**: 場次切換
- **Race Table**: 排位表（桌面/移動端適配）
- **Horse Info**: 馬匹詳情（彩衣、評分、近績）

---

## 功能四：歷史數據與回測

### 4.1 功能描述
保存預測記錄，支持策略回測分析。

### 4.2 數據存儲

#### Predictions Collection
```javascript
{
  race_date: "2026-03-15",
  race_no: 1,
  venue: "ST",
  predictions: [...],
  boosting: { distance: 1.2, jockey: 1.5, ... },
  racecard: {...},
  model_version: "xgb_v1",
  created_at: ISODate()
}
```

### 4.3 回測報告
- **文件**: `backtest_report.json`, `strategy_backtest_report.json`
- **指標**: 勝率、回報率、準確度

### 4.4 數據備份
- **路徑**: `data/backups/`
- **格式**: MongoDB 導出 (BSON + JSON metadata)
- **命名**: `hkjc_racing_backup_YYYY-MM-DD`

---

## 功能交互流程圖

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   HKJC      │────→│   Scrapers  │────→│   MongoDB   │
│  官方網站   │     │  (Playwright)│     │ (數據存儲)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                                │
                       ┌────────────────────────┘
                       ▼
              ┌─────────────────┐
              │  API Server     │
              │   (Port 3001)   │
              │  - REST API     │
              │  - Socket.IO    │
              └────────┬────────┘
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
    ┌─────────────┐          ┌─────────────┐
    │   ML Model  │          │  WebSocket  │
    │  (XGBoost)  │          │   Server    │
    └──────┬──────┘          └──────┬──────┘
           │                        │
           ▼                        ▼
    ┌─────────────┐          ┌─────────────┐
    │ Predictions │          │  Web App    │
    │  (MongoDB)  │          │ (React/Vite)│
    └─────────────┘          └─────────────┘
```

---

## 驗收標準檢查表

- [x] Feature Document 涵蓋四大功能分析
  - [x] 實時賠率收集與 WebSocket 推送
  - [x] AI 預測與因子調整
  - [x] 賽事數據管理與排位表
  - [x] 歷史數據與回測
- [x] Technical Guide 包含啟動方式、數據儲存、架構

---

*文件結束*
