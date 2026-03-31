# HKJC Docker 部署指南

## 系統要求

- macOS 15.x (Apple Silicon/arm64 或 Intel)
- Docker Desktop 4.25+ 
- 至少 8GB RAM (建議 16GB)
- 至少 20GB 可用磁盤空間

---

## 快速開始

### 1. 安裝 Docker Desktop

**Apple Silicon Mac (M1/M2/M3):**
```bash
# 使用 Homebrew 安裝
brew install --cask docker

# 或手動下載
# 訪問: https://docs.docker.com/desktop/install/mac-install/
# 選擇 "Mac with Apple Silicon"
```

**Intel Mac:**
```bash
# 使用 Homebrew 安裝
brew install --cask docker

# 或手動下載 Intel 版本
```

安裝後啟動 Docker Desktop，等待 "Docker Desktop is running" 指示燈變綠。

### 2. 克隆並進入項目

```bash
cd /Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC
```

### 3. 首次設置

```bash
# 創建環境配置文件
./docker-deploy.sh setup

# 編輯 .env 文件 (可選)
nano .env
```

### 4. 構建並啟動

```bash
# 構建所有 Docker 鏡像
./docker-deploy.sh build

# 啟動服務
./docker-deploy.sh start
```

### 5. 驗證部署

```bash
# 查看服務狀態
./docker-deploy.sh status

# 查看日誌
./docker-deploy.sh logs
```

訪問地址:
- **Web App**: http://localhost
- **API**: http://localhost:3001
- **MongoDB**: mongodb://localhost:27017

---

## 常用命令

```bash
# 停止所有服務
./docker-deploy.sh stop

# 重啟服務
./docker-deploy.sh restart

# 進入 API 容器調試
./docker-deploy.sh shell-api

# 進入 MongoDB shell
./docker-deploy.sh shell-db

# 運行 Odds Collector (賽事日)
./docker-deploy.sh collect 2026-03-26 ST
```

---

## 服務架構

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Network                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   Web (80)   │  │  API (3001)  │  │   MongoDB        │  │
│  │  React+Vite  │  │  Node+Python │  │   (27017)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│         │                 │                   │            │
│         └─────────────────┴───────────────────┘            │
│                           │                                │
│              ┌────────────┴────────────┐                   │
│              │   Odds Collector        │                   │
│              │   (Playwright/Chromium) │                   │
│              │   - 賽事日手動啟動      │                   │
│              └─────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 生產環境部署

### 配置 SSL

1. 準備 SSL 證書:
```bash
mkdir -p docker/nginx/ssl
cp your-cert.pem docker/nginx/ssl/cert.pem
cp your-key.pem docker/nginx/ssl/key.pem
```

2. 啟用生產環境配置:
```bash
docker-compose --profile production up -d
```

### 配置外部訪問

編輯 `.env` 文件:
```bash
EXTERNAL_DOMAIN=your-domain.com
ENABLE_SSL=true
```

然後配置端口轉發或反向代理。

---

## 故障排除

### Docker 未運行
```
Cannot connect to the Docker daemon
```
**解決**: 啟動 Docker Desktop 應用

### 端口被佔用
```
Bind for 0.0.0.0:80 failed: port is already allocated
```
**解決**: 
```bash
# 查看佔用端口的進程
sudo lsof -i :80
# 終止進程或修改 docker-compose.yml 中的端口映射
```

### MongoDB 連接失敗
**解決**: 
```bash
# 等待 MongoDB 完全啟動
./docker-deploy.sh logs mongodb

# 檢查 MongoDB 健康狀態
docker-compose exec mongodb mongosh --eval "db.adminCommand('ping')"
```

### Odds Collector 崩潰
**解決**: 確保有足夠內存 (4GB+) 並正確配置 shm-size
```bash
# 查看容器日誌
docker-compose --profile race-day logs odds-collector
```

---

## 數據持久化

數據存儲在 Docker volumes 中:
- `mongodb_data`: MongoDB 數據
- `api_logs`: API 日誌

備份數據:
```bash
# 備份 MongoDB
docker-compose exec mongodb mongodump --out /data/backup/
docker cp hkjc-mongodb:/data/backup ./backup-$(date +%Y%m%d)
```

恢復數據:
```bash
# 恢復 MongoDB
docker cp ./backup-YYYYMMDD hkjc-mongodb:/data/backup
docker-compose exec mongodb mongorestore /data/backup/
```

---

## 開發模式

使用本地代碼掛載進行開發:
```bash
# 啟動開發模式 (代碼修改自動生效)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

---

## 資源需求

| 服務 | CPU | 內存 | 說明 |
|------|-----|------|------|
| MongoDB | 1核 | 1GB | 可根據數據量調整 |
| API | 0.5核 | 512MB | Python + Node.js |
| Web | 0.25核 | 256MB | React 靜態 |
| Odds Collector | 2核 | 4GB | Chromium 需要較多資源 |

---

## 更新日誌

- 2026-03-26: 初始 Docker 配置完成
  - docker-compose.yml 定義了所有服務
  - API Dockerfile (Node.js + Python)
  - Web Dockerfile (React + Nginx)
  - Odds Collector Dockerfile (Playwright/Chromium)
  - MongoDB 配置和初始化腳本
  - 部署腳本和文檔
