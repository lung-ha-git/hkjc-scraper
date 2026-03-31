# HKJC Docker 機器需求評估

**評估日期**: 2026-03-26

---

## 1. 各組件資源需求分析

### 1.1 MongoDB
| 指標 | 開發環境 | 生產環境 | 說明 |
|------|----------|----------|------|
| **Memory** | 1-2 GB | 4-8 GB | WiredTiger 緩存需要內存 |
| **CPU** | 1-2 cores | 2-4 cores | 主要用於索引和查詢 |
| **Storage** | 20 GB | 100 GB+ | 歷史數據增長 |
| **網絡** | 內部網絡 | 內部網絡 | 僅內部服務訪問 |

**數據增長估算**:
- 每場賽事: ~50KB (racecard + entries)
- 賠率數據: ~10KB/場/次 (如每場收集 20 次 = 200KB/場)
- 每年約 800 場賽事 → ~200MB/年 (純文本)
- MongoDB 存儲放大 2-3x → **~600MB-1GB/年**

### 1.2 API Service (Node.js + React)
| 指標 | 開發環境 | 生產環境 | 說明 |
|------|----------|----------|------|
| **Memory** | 512 MB | 1-2 GB | Express + Socket.IO |
| **CPU** | 1 core | 1-2 cores | 主要處理 API 請求 |
| **Storage** | 1 GB | 1 GB | 代碼 + build 文件 |
| **並發** | 10 users | 100+ users | Socket.IO 連接數 |

### 1.3 Odds Collector (Playwright/Chromium) ⚠️ **資源大戶**
| 指標 | 開發環境 | 生產環境 | 說明 |
|------|----------|----------|------|
| **Memory** | 2-4 GB | 4-8 GB | Chromium 每實例 200-500MB |
| **CPU** | 2 cores | 4 cores | 瀏覽器渲染 + JavaScript |
| **Storage** | 500 MB | 500 MB | Playwright + Chromium |
| **運行時間** | 賽事日連續 | 賽事日連續 | 約 6-8 小時/天 |

**Chromium 內存分析**:
```
每個 Chrome 實例 (fresh browser):
- Browser 進程: ~150-200MB
- Renderer 進程: ~100-200MB
- GPU 進程: ~50-100MB
- 總計: ~300-500MB/實例

賽事日運行 (10 場比賽):
- 持續運行會累積多個頁面
- 建議定期重啟容器釋放內存
```

### 1.4 Pipeline (Python + XGBoost) ⚠️ **訓練時高負載**
| 指標 | 開發環境 | 生產環境 | 說明 |
|------|----------|----------|------|
| **Memory** | 2-4 GB | 4-8 GB | XGBoost 訓練需要內存 |
| **CPU** | 2-4 cores | 4-8 cores | 訓練時 CPU 密集型 |
| **Storage** | 2 GB | 5 GB | Python + 模型文件 |
| **運行時間** | 30-60 min | 1-2 hours | 每日一次 |

**XGBoost 資源特點**:
- 訓練時 CPU 佔用率高 (可使用多線程)
- 內存需求與數據集大小成正比
- 非持續運行，每日一次

---

## 2. 總體資源需求

### 2.1 最低配置 (開發/測試)

```yaml
# 適合: 本地開發、單用戶測試

CPU: 4 cores
Memory: 8 GB
Storage: 50 GB SSD
Network: 寬帶連接 (10Mbps+)

分配:
  - MongoDB:     2 GB RAM, 1 core
  - API:         1 GB RAM, 1 core
  - Odds:        2 GB RAM, 1 core (賽事日運行)
  - Pipeline:    2 GB RAM, 1 core (每日運行)
  - OS/Docker:   1 GB RAM, 1 core
```

**⚠️ 注意**: 此配置在賽事日 + Pipeline 同時運行時會卡頓

### 2.2 推薦配置 (小型生產)

```yaml
# 適合: 5-10 用戶、穩定運行

CPU: 6-8 cores
Memory: 16 GB
Storage: 100 GB SSD
Network: 穩定寬帶 (20Mbps+)

分配:
  - MongoDB:     4 GB RAM, 2 cores
  - API:         2 GB RAM, 2 cores
  - Odds:        4 GB RAM, 2 cores
  - Pipeline:    4 GB RAM, 2 cores (限時運行)
  - OS/Docker:   2 GB RAM, 2 cores
```

### 2.3 標準生產配置

```yaml
# 適合: 50+ 用戶、高可用

CPU: 8-12 cores
Memory: 32 GB
Storage: 200 GB SSD
Network: 商業寬帶 (50Mbps+)

分配:
  - MongoDB:     8 GB RAM, 4 cores
  - API:         4 GB RAM, 2 cores
  - Odds:        8 GB RAM, 4 cores
  - Pipeline:    8 GB RAM, 4 cores
  - OS/Docker:   4 GB RAM, 2 cores
```

---

## 3. 成本估算 (VPS/雲服務器)

### 3.1 開發測試環境

| 平台 | 配置 | 價格 (月) |
|------|------|-----------|
| DigitalOcean | 4 vCPU / 8 GB | ~$48 |
| AWS Lightsail | 4 vCPU / 8 GB | ~$40 |
| Hetzner | 4 vCPU / 16 GB | ~$20 |
| Linode | 4 GB / 8 GB | ~$48 |
| 騰訊雲 | 4核 / 8 GB | ~¥200 |
| 阿里雲 | 4核 / 8 GB | ~¥250 |

### 3.2 生產環境

| 平台 | 配置 | 價格 (月) |
|------|------|-----------|
| DigitalOcean | 8 vCPU / 32 GB | ~$160 |
| AWS EC2 (t3.xlarge) | 4 vCPU / 16 GB | ~$120 |
| Hetzner | 8 vCPU / 32 GB | ~$40 |
| 騰訊雲 | 8核 / 32 GB | ~¥600 |
| 阿里雲 | 8核 / 32 GB | ~¥800 |

**推薦**: Hetzner (性價比最高) 或 騰訊雲/阿里雲 (國內訪問快)

---

## 4. 優化建議

### 4.1 內存優化

```yaml
# docker-compose.yml 資源限制
services:
  mongodb:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G

  odds-collector:
    deploy:
      resources:
        limits:
          memory: 4G  # 防止 Chromium 內存洩漏
        reservations:
          memory: 2G
    # 賽事日後自動重啟
    restart: unless-stopped

  pipeline:
    deploy:
      resources:
        limits:
          memory: 8G
          cpus: '4.0'
```

### 4.2 存儲優化

```yaml
# MongoDB 數據清理策略
# 1. 定期壓縮歷史賠率 (只保留每場比賽的關鍵時間點)
# 2. 冷數據存檔 (超過 1 年的數據移到廉價存儲)

# 使用 Docker Volume 管理
volumes:
  mongo_data:
    driver: local
  mongo_backup:
    driver: local
```

### 4.3 CPU 優化

```python
# Pipeline 訓練時限制 CPU
# daily_pipeline.py
import os
os.environ['OMP_NUM_THREADS'] = '4'  # 限制 XGBoost 線程數
```

---

## 5. 擴展方案

### 5.1 水平擴展 (Scale Out)

當單機無法滿足時:

```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                        │
│                      (Nginx)                            │
└──────────────┬────────────────────────────┬─────────────┘
               │                            │
        ┌──────▼──────┐              ┌──────▼──────┐
        │  HKJC-API-1 │              │  HKJC-API-2 │
        │   Node.js   │              │   Node.js   │
        └──────┬──────┘              └──────┬──────┘
               │                            │
               └────────────┬───────────────┘
                            │
                    ┌───────▼────────┐
                    │    MongoDB     │
                    │  (Replica Set) │
                    └────────────────┘
```

**分離部署**:
- MongoDB: 獨立服務器 (4-8 GB RAM)
- API Servers: 多台小機器 (2-4 GB RAM each)
- Workers: 按需啟動 (Spot instances)

### 5.2 Kubernetes 方案 (大規模)

```yaml
# 適合: 100+ 並發用戶

Nodes:
  - 3x Master (2 vCPU / 4 GB)
  - 3x Worker (4 vCPU / 16 GB)

Pods:
  - MongoDB StatefulSet: 1 replica, 8 GB
  - API Deployment: 3 replicas, 2 GB each
  - Odds Job: 按需創建, 4 GB
  - Pipeline CronJob: 定時觸發, 8 GB
```

---

## 6. 總結

### 開發環境
- **最低**: 4核 / 8GB / 50GB SSD (~$40-50/月)
- **推薦**: 4核 / 16GB / 100GB SSD (~$60-80/月)

### 生產環境
- **最低**: 6核 / 16GB / 100GB SSD (~$80-100/月)
- **推薦**: 8核 / 32GB / 200GB SSD (~$150-200/月)
- **企業**: K8s 集群 (~$300+/月)

### 成本優化技巧
1. **使用 Hetzner** (比 AWS/GCP 便宜 50%+)
2. **Odds Collector 按需運行** (只在賽事日啟動)
3. **Pipeline 定時運行** (使用 Cron Job 而非持續運行)
4. **MongoDB 數據清理** (定期刪除/壓縮舊數據)
5. **使用 Swap** (小內存機器可配置 4-8GB Swap)
