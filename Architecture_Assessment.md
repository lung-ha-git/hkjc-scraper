# HKJC 系統架構評估報告

**評估日期**: 2026-03-26  
**評估項目**:
1. Daily Routine + WebApp + Odds Server 整合為單一 Service
2. Model 持續 Training 方案
3. Container 化可行性

---

## 1. 現有架構分析

### 1.1 當前服務組件

| 組件 | 技術 | 端口 | 職責 | 運行模式 |
|------|------|------|------|----------|
| **Frontend** | React + Vite | 3000 | 用戶界面 | Dev Server |
| **API Server** | Node.js + Express + Socket.IO | 3001 | REST API + WebSocket | Persistent |
| **Odds Collector** | Playwright (Node.js) | - | 實時賠率爬蟲 | Cron/Continuous |
| **Daily Pipeline** | Python | - | 數據同步 + 模型訓練 | Cron (1x/day) |
| **MongoDB** | MongoDB | 27017 | 數據存儲 | Persistent |

### 1.2 依賴關係圖

```
┌─────────────────────────────────────────────────────────────────┐
│                        用戶/管理員                               │
└──────────────┬──────────────────────────────┬───────────────────┘
               │                              │
        ┌──────▼──────┐                ┌─────▼──────┐
        │  Frontend   │                │   Admin    │
        │   :3000     │                │   (Cron)   │
        └──────┬──────┘                └─────┬──────┘
               │                              │
               │        ┌──────────────┐      │
               └───────►│  API Server  │◄─────┘
                        │   :3001      │
                        └──────┬───────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        ┌──────────┐    ┌──────────┐    ┌──────────┐
        │ MongoDB  │    │  Python  │    │ Playwright│
        │ :27017   │    │ Pipeline │    │  Odds    │
        └──────────┘    └──────────┘    └──────────┘
```

---

## 2. 整合為單一 Service 評估

### 2.1 可行性: ✅ 可行，但需權衡

**整合方案**:
```
┌─────────────────────────────────────────────────────────────┐
│                    HKJC Unified Service                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Web App   │  │  API Server │  │   Worker Threads    │ │
│  │  (React)    │  │  (Express)  │  │  ┌───────────────┐  │ │
│  │             │  │             │  │  │ Odds Collector│  │ │
│  │  Port 80    │  │  Port 3001  │  │  │ (Playwright)  │  │ │
│  └─────────────┘  └─────────────┘  │  └───────────────┘  │ │
│                                     │  ┌───────────────┐  │ │
│                                     │  │Daily Pipeline │  │ │
│                                     │  │   (Python)    │  │ │
│                                     │  └───────────────┘  │ │
│                                     └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 整合優缺點

| 優點 | 缺點 |
|------|------|
| 單一部署單元，簡化運維 | 單點故障風險增加 |
| 統一日誌和監控 | 資源隔離性降低 |
| 減少端口暴露 | Playwright 內存洩漏影響整體服務 |
| 共享 MongoDB 連接池 | Python/Node 進程間通信複雜 |

### 2.3 推薦方案: **部分整合**

```
Service A: Web + API (Node.js) ───┐
                                   ├──► MongoDB
Service B: Workers (Python) ──────┘

Service A (Node.js):
  - Frontend (React build)
  - API Server (Express)
  - Odds Collector (child_process spawn)

Service B (Python):
  - Daily Pipeline
  - Model Training
  - Background Jobs
```

---

## 3. Model 持續 Training 方案

### 3.1 現有 Pipeline

`daily_pipeline.py`:
1. Sync fixtures (賽事日曆)
2. Scrape racecards (排位表)
3. Sync past results (歷史結果)
4. **Train model** (if new data)
5. Push to GitHub

### 3.2 持續 Training 架構

```
┌─────────────────────────────────────────────────────────────┐
│                   Model Training Pipeline                   │
├─────────────────────────────────────────────────────────────┤
│  Trigger: Cron (Daily 6AM) 或 Event-driven (new results)   │
│                                                             │
│  Step 1: Check Data Drift                                  │
│     ├─ Compare new race results vs training distribution   │
│     └─ If drift > threshold → trigger retrain              │
│                                                             │
│  Step 2: Feature Engineering                               │
│     ├─ Update horse career stats                           │
│     ├─ Update jockey/trainer form                          │
│     └─ Generate new features                               │
│                                                             │
│  Step 3: Model Retrain                                     │
│     ├─ Retrain XGBoost with new data                       │
│     ├─ Cross-validation                                    │
│     └─ Compare with previous model (A/B test)              │
│                                                             │
│  Step 4: Model Deployment                                  │
│     ├─ Save model: `models/xgb_v{version}.pkl`            │
│     ├─ Update config: `config/model-config.json`          │
│     └─ Hot-reload (if performance ↑)                       │
│                                                             │
│  Step 5: Notification                                      │
│     ├─ Log metrics                                         │
│     └─ Alert if accuracy ↓                                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 推薦實現

```python
# src/training/auto_trainer.py
class AutoTrainer:
    def __init__(self):
        self.drift_threshold = 0.1
        self.min_accuracy_improvement = 0.01
    
    def should_retrain(self) -> bool:
        # 檢查新數據量或漂移
        new_races = self.get_untrained_races()
        return len(new_races) >= 10  # 至少10場新賽事
    
    def retrain(self) -> ModelMetrics:
        # 保留舊模型作為 fallback
        self.backup_current_model()
        
        # 訓練新模型
        new_model = self.train_ensemble()
        metrics = self.evaluate(new_model)
        
        # A/B 測試邏輯
        if metrics.accuracy > self.current_accuracy + self.min_accuracy_improvement:
            self.deploy(new_model)
            return metrics
        else:
            self.rollback()
            return None
```

---

## 4. Container 化評估

### 4.1 可行性: ✅ **強烈推薦**

**Docker Compose 架構**:
```yaml
# docker-compose.yml
version: '3.8'

services:
  # 1. MongoDB
  mongodb:
    image: mongo:7.0
    volumes:
      - mongo_data:/data/db
    ports:
      - "27017:27017"

  # 2. Web + API (Node.js)
  hkjc-api:
    build: ./docker/api
    ports:
      - "80:3000"      # Frontend (built)
      - "3001:3001"    # API + Socket.IO
    environment:
      - MONGODB_URI=mongodb://mongodb:27017/hkjc_racing
      - NODE_ENV=production
    depends_on:
      - mongodb
    restart: unless-stopped

  # 3. Odds Collector (Playwright)
  odds-collector:
    build: ./docker/odds-collector
    environment:
      - API_BASE=http://hkjc-api:3001
      - MONGODB_URI=mongodb://mongodb:27017/hkjc_racing
    depends_on:
      - mongodb
      - hkjc-api
    # 只在賽事日運行
    profiles: ["race-day"]

  # 4. Daily Pipeline + Training (Python)
  pipeline:
    build: ./docker/pipeline
    environment:
      - MONGODB_URI=mongodb://mongodb:27017/hkjc_racing
      - GITHUB_TOKEN=${GITHUB_TOKEN}
    depends_on:
      - mongodb
    # 定時觸發或手動執行
    profiles: ["pipeline"]

volumes:
  mongo_data:
```

### 4.2 Dockerfile 示例

**API Service**:
```dockerfile
# docker/api/Dockerfile
FROM node:20-alpine

WORKDIR /app

# 安裝依賴
COPY web-app/package*.json ./
RUN npm ci --only=production

# 構建前端
COPY web-app/ ./
RUN npm run build

# 複製 API server
COPY web-app/server ./server

EXPOSE 3000 3001

CMD ["node", "server/index.cjs"]
```

**Odds Collector**:
```dockerfile
# docker/odds-collector/Dockerfile
FROM mcr.microsoft.com/playwright:v1.40.0-jammy

WORKDIR /app

COPY scrapers/odds_collector.js ./
COPY scrapers/package*.json ./
RUN npm install

# Playwright 需要特權模式運行 Chromium
CMD ["node", "odds_collector.js", "${RACE_DATE}", "${VENUE}", "--continuous"]
```

**Pipeline**:
```dockerfile
# docker/pipeline/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . ./

CMD ["python3", "daily_pipeline.py"]
```

### 4.3 Container 化優勢

| 優勢 | 說明 |
|------|------|
| **環境一致性** | 開發/測試/生產完全一致 |
| **簡化部署** | `docker-compose up -d` 一鍵啟動 |
| **資源隔離** | Playwright 內存洩漏不影響其他服務 |
| **水平擴展** | 可擴展多個 odds-collector 實例 |
| **版本控制** | 模型/代碼版本與 Image 綁定 |

### 4.4 注意事項

```yaml
# 賽事日啟動 odds-collector
docker-compose --profile race-day up -d

# 手動觸發 pipeline
docker-compose --profile pipeline run --rm pipeline

# 設置定時任務 (host cron)
0 6 * * * cd /path/to/hkjc && docker-compose --profile pipeline run --rm pipeline
```

---

## 5. 推薦架構 (Container + 部分整合)

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │   MongoDB       │    │      HKJC-API (Node.js)         │ │
│  │   :27017        │◄──►│  ┌─────────────┐ ┌────────────┐ │ │
│  │                 │    │  │  Frontend   │ │ API Server │ │ │
│  └─────────────────┘    │  │  (React)    │ │ (Express)  │ │ │
│           ▲             │  │  :80        │ │ :3001      │ │ │
│           │             │  └─────────────┘ └────────────┘ │ │
│           │             └─────────────────────────────────┘ │
│           │                                                 │
│           │             ┌─────────────────────────────────┐ │
│           │             │   Odds-Collector (Playwright)   │ │
│           └────────────►│   - Profile: race-day           │ │
│                         │   - Spawn on demand             │ │
│                         └─────────────────────────────────┘ │
│                                                             │
│                         ┌─────────────────────────────────┐ │
│                         │   Pipeline (Python)             │ │
│                         │   - Daily sync                  │ │
│                         │   - Model training              │ │
│                         │   - Profile: pipeline           │ │
│                         └─────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 實施建議

### Phase 1: Dockerize (1-2 天)
1. 創建 `docker/` 目錄和 Dockerfile
2. 編寫 `docker-compose.yml`
3. 本地測試

### Phase 2: CI/CD (1 天)
1. GitHub Actions build images
2. Push to registry

### Phase 3: Model Training 優化 (2-3 天)
1. 實現 drift detection
2. A/B testing 框架
3. Hot-reload 機制

### Phase 4: 監控 (1 天)
1. Prometheus metrics
2. Grafana dashboard
3. Alerting rules

---

## 7. 總結

| 項目 | 評估 | 建議 |
|------|------|------|
| **整合為單一 Service** | ⚠️ 部分可行 | 分離 Worker 進程，API 整合 Frontend |
| **Model 持續 Training** | ✅ 推薦 | 基於 drift detection 的自動重訓練 |
| **Container 化** | ✅ **強烈推薦** | Docker Compose + 多服務分離 |

**最終建議**: 採用 Docker Compose 架構，將系統分為 4 個容器化服務（MongoDB、API、Odds Collector、Pipeline），實現資源隔離、簡化部署和持續訓練。
