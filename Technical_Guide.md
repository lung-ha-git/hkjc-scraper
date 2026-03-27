# HKJC AI 預測系統 - Technical Guide

## 文件資訊
- **版本**: v1.0
- **作者**: Dev_Alpha
- **日期**: 2026-03-26
- **狀態**: 完成 (TASK-001)

---

## 目錄
1. [系統架構](#1-系統架構)
2. [啟動方式](#2-啟動方式)
3. [數據儲存架構](#3-數據儲存架構)
4. [API 參考](#4-api-參考)
5. [配置說明](#5-配置說明)

---

## 1. 系統架構

### 1.1 技術棧

| 層級 | 技術 | 版本 |
|------|------|------|
| 前端 | React + Vite | React 18, Vite 5 |
| 後端 | Node.js + Express | Express 5.2 |
| 數據庫 | MongoDB | 7.x |
| 爬蟲 | Playwright | Chromium |
| 實時通信 | Socket.IO | 4.8 |
| 圖表 | Chart.js | 4.5 |

### 1.2 服務架構

```
┌─────────────────────────────────────────────────────────────┐
│                        前端層 (Port 3000)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   App.jsx    │  │ UnifiedRace  │  │  useOdds     │     │
│  │   (主組件)   │  │   Table.jsx  │  │  Socket.js   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ Proxy
┌─────────────────────────────────────────────────────────────┐
│                       API 層 (Port 3001)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  REST API    │  │  Socket.IO   │  │  ML Predict  │     │
│  │  /api/*      │  │  /socket.io  │  │  /predict    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    MongoDB      │  │   Playwright    │  │   XGBoost       │
│  (Port 27017)   │  │   (Scrapers)    │  │   (Python)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 1.3 目錄結構

```
Projects/HKJC/src/
├── web-app/                    # 前端應用
│   ├── src/
│   │   ├── App.jsx            # 主應用組件
│   │   ├── hooks/
│   │   │   └── useOddsSocket.js  # WebSocket Hook
│   │   └── components/
│   │       ├── OddsPanel.jsx
│   │       └── UnifiedRaceTable.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── scrapers/                   # 數據爬蟲
│   ├── odds_collector.js      # 實時賠率收集
│   ├── graphql_racecards.js   # GraphQL 賽事數據
│   ├── hybrid_odds_scraper.js
│   └── validate_entries.js
│
├── config/                     # 配置文件
│   └── model-config.json      # 模型配置
│
├── data/                       # 數據備份
│   └── backups/               # MongoDB 備份
│
├── docs/                       # 文檔
│
├── models/                     # ML 模型
│   └── ensemble_v1_config.json
│
└── logs/                       # 日誌文件
```

---

## 2. 啟動方式

### 2.1 前置需求

```bash
# 1. MongoDB 運行中
mongod --dbpath /path/to/data

# 2. Node.js 環境
node --version  # >= 18.x

# 3. Playwright 瀏覽器
npx playwright install chromium
```

### 2.2 完整啟動流程

#### 步驟 1：進入項目目錄
```bash
cd /Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC/src
```

#### 步驟 2：啟動 MongoDB（如未運行）
```bash
mongod --dbpath /usr/local/var/mongodb
```

#### 步驟 3：啟動 API 服務器 (Terminal 1)
```bash
cd web-app
npm install
node server.js  # Port 3001
```

#### 步驟 4：啟動前端開發服務器 (Terminal 2)
```bash
cd web-app
npm run dev     # Port 3000
```

#### 步驟 5：啟動賠率收集器（可選，賽事日）
```bash
node ../scrapers/odds_collector.js 2026-03-26 ST --continuous --interval 10000
```

### 2.3 服務端口配置

| 服務 | 端口 | 配置位置 |
|------|------|----------|
| 前端開發服務器 | 3000 | `vite.config.js` |
| API 服務器 | 3001 | `web-app/server.js` |
| MongoDB | 27017 | 默認 |
| Socket.IO | 3001 (共享) | `server.js` |

---

## 3. 數據儲存架構

### 3.1 MongoDB 數據庫結構

```
hkjc_racing_dev (數據庫名稱)
│
├── races                        # 賽事主表
│   ├── hkjc_race_id: "2026_03_15_ST_1"
│   ├── race_date: "2026/03/15"
│   ├── venue: "ST"
│   ├── race_no: "1"
│   ├── distance: "1000米"
│   ├── class: "五班"
│   ├── track_condition: "好地至快地"
│   ├── entries: [ {...} ]
│   ├── results: [ {...} ]
│   └── payout: { ... }
│
├── horses                       # 馬匹資料
│   ├── hkjc_horse_id: "HK_2025_L108"
│   ├── name: "紫荊傳令"
│   ├── jersey_url: ".../L108.gif"
│   ├── current_rating: 79
│   └── trainer: "游達榮"
│
├── jockeys                      # 騎師統計
│   ├── jockey_id: "PZ"
│   ├── name: "潘頓"
│   └── season: "2025/2026"
│
├── trainers                     # 練馬師統計
├── live_odds                    # 實時賠率記錄
├── predictions                  # AI 預測記錄
├── fixtures                     # 賽事日程
└── scraping_queue               # 爬蟲任務隊列
```

### 3.2 主要 Collections

| Collection | 用途 | 關鍵索引 |
|------------|------|----------|
| `races` | 賽事數據 | `race_date + venue`, `hkjc_race_id` |
| `horses` | 馬匹資料 | `hkjc_horse_id`, `name` |
| `jockeys` | 騎師統計 | `jockey_id` |
| `trainers` | 練馬師統計 | `trainer_id` |
| `live_odds` | 實時賠率 | `race_id + scraped_at` |
| `predictions` | AI 預測 | `race_date + race_no` |

### 3.3 備份策略

```bash
# 手動備份
mongodump --db hkjc_racing_dev --out ./data/backups/hkjc_racing_backup_$(date +%Y-%m-%d)

# 恢復備份
mongorestore --db hkjc_racing_dev ./data/backups/hkjc_racing_backup_2026-03-10/
```

---

## 4. API 參考

### 4.1 REST API

| 端點 | 方法 | 描述 |
|------|------|------|
| `/api/fixtures` | GET | 獲取賽事日程 |
| `/api/racecards?date=` | GET | 獲取排位表 |
| `/api/predict` | GET | 獲取 AI 預測 |
| `/api/predictions` | POST | 保存預測結果 |
| `/api/odds/snapshot` | POST | 接收賠率快照 |
| `/api/odds/batch-snapshot` | POST | 批量接收賠率 |

### 4.2 WebSocket 事件

**客戶端 → 服務器**
```javascript
socket.emit('subscribe', { race_id: "2026-03-22_ST_R7" });
socket.emit('unsubscribe', { race_id: "2026-03-22_ST_R7" });
```

**服務器 → 客戶端**
```javascript
// 賠率更新
socket.on('odds_update', (data) => {
  // { horse_no: 1, win: 12.5, place: 3.5, timestamp: 1234567890 }
});

// 完整快照
socket.on('odds_snapshot', (data) => {
  // { odds: { "1": { win: 12.5, place: 3.5 } }, session: {...} }
});
```

---

## 5. 配置說明

### 5.1 模型配置 (`config/model-config.json`)

```json
{
  "models": {
    "xgb-default": {
      "features": 23,
      "accuracy": 0.567,
      "status": "active"
    }
  },
  "settings": {
    "default_model": "xgb-default",
    "timeout_seconds": 60,
    "enable_boosting": true
  }
}
```

### 5.2 Vite 代理配置

```javascript
proxy: {
  '/api': { target: 'http://127.0.0.1:3001', changeOrigin: true },
  '/socket.io': { target: 'http://127.0.0.1:3001', ws: true }
}
```

### 5.3 環境變量配置 (`.env`)

```bash
# MongoDB 配置
MONGODB_ROOT_PASSWORD=your_secure_password

# Pipeline 配置（可選）
RACE_DATE=2026-03-29    # 指定抓取日期
VENUE=ST                # 指定賽場 (ST/HV)
```

| 變量 | 說明 | 預設值 |
|------|------|---------|
| `MONGODB_ROOT_PASSWORD` | MongoDB root 密碼 | `changeme_default_password` |
| `RACE_DATE` | 指定抓取日期 (YYYY-MM-DD) | 當天 |
| `VENUE` | 賽場 (`ST` 沙田 / `HV` 跑馬地) | - |

**注意**：`.env` 文件不應提交到 Git，已在 `.gitignore` 中排除。

---

*文件結束*
