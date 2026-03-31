# HKJC Docker 安裝與啟動完整指南

**版本**: 1.0  
**更新日期**: 2026-03-26  
**適用平台**: macOS (Apple Silicon/arm64 & Intel)  

---

## 📋 目錄

1. [系統要求](#系統要求)
2. [Docker Desktop 安裝](#docker-desktop-安裝)
3. [首次運行初始化](#首次運行初始化)
4. [日常啟動/停止](#日常啟動停止)
5. [互聯網訪問配置](#互聯網訪問配置)
6. [常見問題排查](#常見問題排查)

---

## 系統要求

### 最低配置

| 項目 | 要求 |
|------|------|
| **操作系統** | macOS 13.0+ (Ventura) |
| **處理器** | Apple Silicon (M1/M2/M3) 或 Intel |
| **內存** | 8 GB RAM |
| **磁盤空間** | 20 GB 可用空間 |
| **網絡** | 寬帶連接 (10Mbps+) |

### 推薦配置

| 項目 | 建議 |
|------|------|
| **操作系統** | macOS 15.x (Sequoia) |
| **處理器** | Apple Silicon (M2/M3) |
| **內存** | 16 GB RAM |
| **磁盤空間** | 50 GB 可用空間 (SSD) |
| **網絡** | 穩定寬帶 (20Mbps+) |

---

## Docker Desktop 安裝

### 方法一：使用 Homebrew (推薦)

```bash
# 1. 安裝 Homebrew (如未安裝)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. 安裝 Docker Desktop
brew install --cask docker

# 3. 啟動 Docker Desktop
open /Applications/Docker.app
```

### 方法二：手動下載安裝

1. 訪問官方下載頁面: https://docs.docker.com/desktop/install/mac-install/
2. 選擇對應版本：
   - **Apple Silicon Mac (M1/M2/M3)**: 選擇 "Mac with Apple Chip"
   - **Intel Mac**: 選擇 "Mac with Intel Chip"
3. 下載 `.dmg` 文件並安裝
4. 將 Docker.app 拖入 Applications 文件夾
5. 從 Applications 啟動 Docker Desktop

### 驗證安裝

等待 Docker Desktop 啟動完成（菜單欄顯示 🐳 圖標），然後運行：

```bash
# 檢查 Docker 版本
docker --version
# 預期輸出: Docker version 24.x.x or higher

# 檢查 Docker Compose 版本
docker compose version
# 預期輸出: Docker Compose version v2.x.x or higher

# 運行測試容器
docker run --rm hello-world
# 預期輸出: Hello from Docker!
```

### Docker Desktop 初始配置

1. 打開 Docker Desktop → Settings (⚙️)
2. **General** 標籤：
   - ✅ 勾選 "Start Docker Desktop when you log in"
   - ✅ 勾選 "Use Virtualization framework" (Apple Silicon)
3. **Resources** 標籤：
   - **CPU**: 至少 4 核 (推薦 6-8 核)
   - **Memory**: 至少 8 GB (推薦 12-16 GB)
   - **Swap**: 2 GB
   - **Disk**: 至少 64 GB
4. **Apply & Restart**

---

## 首次運行初始化

### 步驟 1：進入項目目錄

```bash
cd /Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC
```

### 步驟 2：創建環境配置文件

```bash
# 複製環境模板
cp .env.example .env

# 編輯 .env 文件 (使用你喜歡的編輯器)
nano .env
# 或 vim .env
# 或 open -e .env  (使用 TextEdit)
```

### 步驟 3：配置環境變量

編輯 `.env` 文件，**務必修改密碼**：

```bash
# MongoDB 配置 (⚠️ 重要：請更改默認密碼)
MONGODB_ROOT_PASSWORD=你的強密碼123!
MONGODB_APP_PASSWORD=你的應用密碼456!

# 其他配置保持默認即可
API_PORT=3001
NODE_ENV=production
WEB_PORT=80
TZ=Asia/Hong_Kong
```

### 步驟 4：構建 Docker 鏡像

```bash
# 方法一：使用部署腳本 (推薦)
./docker-deploy.sh build

# 方法二：直接使用 docker compose
docker compose build --no-cache
```

預計構建時間：
- **首次構建**: 5-10 分鐘 (下載基礎鏡像)
- **後續構建**: 2-5 分鐘

### 步驟 5：啟動服務

```bash
# 方法一：使用部署腳本
./docker-deploy.sh start

# 方法二：使用 docker/start.sh 腳本
./docker/start.sh

# 方法三：直接使用 docker compose
docker compose up -d mongodb api web
```

### 步驟 6：驗證啟動

```bash
# 查看服務狀態
./docker-deploy.sh status
# 或使用
./docker/status.sh
```

預期輸出：
```
NAME            STATUS          PORTS
hkjc-mongodb    Up 30 seconds   0.0.0.0:27017->27017/tcp
hkjc-api        Up 25 seconds   0.0.0.0:3001->3001/tcp
hkjc-web        Up 20 seconds   0.0.0.0:80->80/tcp
```

### 步驟 7：訪問 WebApp

打開瀏覽器訪問：

- **Web 應用**: http://localhost
- **API 端點**: http://localhost:3001
- **API 健康檢查**: http://localhost:3001/health

---

## 日常啟動停止

### 快速啟動 (推薦)

```bash
# 一鍵啟動所有服務
cd /Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC
./docker/start.sh
```

### 快速停止

```bash
# 一鍵停止所有服務
./docker/stop.sh
```

### 常用命令速查

| 操作 | 命令 |
|------|------|
| **啟動** | `./docker/start.sh` |
| **停止** | `./docker/stop.sh` |
| **重啟** | `./docker-deploy.sh restart` |
| **查看狀態** | `./docker/status.sh` |
| **查看日誌** | `./docker/logs.sh` |
| **進入 API 容器** | `./docker-deploy.sh shell-api` |
| **進入數據庫** | `./docker-deploy.sh shell-db` |

---

## 互聯網訪問配置

為了讓外部網絡訪問你的 WebApp，有三種方案：

### 方案一：ngrok (最簡單，適合測試)

**優點**: 免費、5分鐘設置、無需域名  
**缺點**: 免費版每次重啟 URL 會變、有流量限制

```bash
# 安裝 ngrok
brew install ngrok

# 註冊並配置 Token (從 https://ngrok.com 獲取)
ngrok config add-authtoken 你的_TOKEN

# 啟動隧道 (暴露本地 80 端口)
ngrok http 80
```

輸出示例：
```
Forwarding  https://abc123-def.ngrok-free.app -> http://localhost:80
```

**訪問地址**: `https://abc123-def.ngrok-free.app`

---

### 方案二：Cloudflare Tunnel (推薦，免費穩定)

**優點**: 免費、固定域名、無需公開 IP、自帶 SSL  
**缺點**: 需要註冊 Cloudflare 帳號

```bash
# 1. 安裝 cloudflared
brew install cloudflared

# 2. 登入並授權
cloudflared tunnel login

# 3. 創建隧道
cloudflared tunnel create hkjc

# 4. 添加 DNS 記錄
cloudflared tunnel route dns hkjc hkjc.你的域名.com

# 5. 配置隧道 (編輯 ~/.cloudflared/config.yml)
# 6. 啟動隧道
cloudflared tunnel run hkjc
```

**訪問地址**: `https://hkjc.你的域名.com`

---

### 方案三：路由器端口轉發 (需要固定 IP)

**優點**: 無需第三方服務、完全控制  
**缺點**: 需要公網 IP、配置較複雜

1. 登入路由器管理界面
2. 找到 "端口轉發" 設置
3. 添加規則：外部端口 80 → 內部 IP:80

**訪問地址**: `http://你的公網IP:80`

---

## 常見問題排查

### ❌ Docker Desktop 無法啟動

```bash
# 完全退出並重啟
pkill Docker
rm -rf ~/Library/Containers/com.docker.docker
open /Applications/Docker.app
```

### ❌ "Cannot connect to the Docker daemon"

```bash
# 確認 Docker Desktop 已啟動
open -a Docker
sleep 10
docker info
```

### ❌ 端口被佔用

```bash
# 查找佔用端口的進程
sudo lsof -i :80
# 終止進程或修改 docker-compose.yml 使用其他端口
```

### ❌ MongoDB 連接失敗

```bash
# 查看日誌
docker compose logs mongodb

# 重置數據卷
docker compose down -v
docker compose up -d
```

### ❌ WebApp 無法訪問

```bash
# 檢查所有服務狀態
./docker/status.sh

# 檢查 Web 日誌
docker compose logs web

# 檢查 API 日誌
docker compose logs api
```

---

## 附錄

### 完整腳本清單

| 腳本 | 用途 |
|------|------|
| `./docker/start.sh` | 一鍵啟動所有服務 |
| `./docker/stop.sh` | 一鍵停止所有服務 |
| `./docker/status.sh` | 查看服務狀態 |
| `./docker/logs.sh` | 查看日誌 |
| `./docker-deploy.sh` | 完整部署腳本 |

### 端口說明

| 端口 | 服務 | 用途 |
|------|------|------|
| 80 | Web | 前端應用 |
| 3001 | API | 後端 API |
| 27017 | MongoDB | 數據庫 |

### 資源需求

| 服務 | CPU | 內存 |
|------|-----|------|
| MongoDB | 1核 | 1-2GB |
| API | 0.5核 | 512MB |
| Web | 0.25核 | 256MB |
| **總計** | **2核** | **3GB+** |

---

**文檔版本**: 1.0  
**最後更新**: 2026-03-26  
**維護者**: The_Tester