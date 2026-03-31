# Docker 中運行 Chromium/Playwright 技術指南

## 問題背景

Playwright/Chromium 在 Docker 中運行面臨的挑戰：
1. **Chromium 沙盒** - 預設需要 root 權限，Docker 容器中通常以非 root 運行
2. **系統依賴** - Chromium 需要大量系統庫（fonts, GPU drivers, etc.）
3. **資源限制** - Docker 容器資源限制可能導致瀏覽器崩潰
4. **無頭模式** - 容器環境無顯示設備，必須使用 headless

---

## 方案一：官方 Playwright Image（推薦）

Microsoft 提供官方 Docker image，已預裝所有依賴：

```dockerfile
# docker/odds-collector/Dockerfile
FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app

# 複製代碼
COPY scrapers/odds_collector.js ./
COPY scrapers/package*.json ./
RUN npm install

# 預設以非 root 用戶運行 (pwuser)
USER pwuser

# 禁用 Chromium 沙盒 (必須在無頭模式下)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

CMD ["node", "odds_collector.js"]
```

**docker-compose.yml**:
```yaml
services:
  odds-collector:
    build: ./docker/odds-collector
    environment:
      - RACE_DATE=${RACE_DATE}
      - VENUE=${VENUE}
      - API_BASE=http://api:3001
    # 關鍵：Chromium 需要特定權限
    cap_add:
      - SYS_ADMIN  # 用於命名空間
    security_opt:
      - seccomp:unconfined  # 或自定義 seccomp profile
    shm_size: '2gb'  # 增加共享內存，防止瀏覽器崩潰
    deploy:
      resources:
        limits:
          memory: 4G
    profiles: ["race-day"]
```

---

## 方案二：輕量級 Alpine Image

如果希望鏡像更小，可使用 Alpine + Chromium：

```dockerfile
# docker/odds-collector/Dockerfile.alpine
FROM node:18-alpine

# 安裝 Chromium 和依賴
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    freetype-dev \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    # 用於視頻錄製
    ffmpeg

WORKDIR /app

COPY scrapers/ ./
RUN npm install

# 告訴 Playwright 使用系統 Chromium
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Chromium 在 Docker 中必須禁用沙盒
ENV CHROMIUM_FLAGS="--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage"

CMD ["node", "odds_collector.js"]
```

**odds_collector.js 修改**:
```javascript
const browser = await chromium.launch({
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',  // 關鍵：避免 /dev/shm 太小導致崩潰
    '--disable-gpu',
    '--disable-web-security',
    '--disable-features=IsolateOrigins,site-per-process',
  ],
  // Alpine 需要指定 executablePath
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
});
```

---

## 方案三：使用 Puppeteer 替代（更輕量）

如果只需要簡單爬蟲，Puppeteer 體積更小：

```dockerfile
FROM node:18-slim

# 安裝依賴
RUN apt-get update && apt-get install -y \
    chromium \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-thai-tlwg \
    fonts-kacst \
    fonts-freefont-ttf \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

CMD ["node", "scraper.js"]
```

---

## 關鍵配置參數

### 1. Docker 運行參數

```bash
# 手動運行容器
docker run -d \
  --name odds-collector \
  --cap-add=SYS_ADMIN \
  --security-opt seccomp=unconfined \
  --shm-size=2gb \
  --memory=4g \
  --memory-swap=4g \
  -e RACE_DATE=2026-03-26 \
  -e VENUE=ST \
  hkjc-odds-collector
```

### 2. 共享內存 (shm-size) 的重要性

```
問題: Chromium 預設使用 /dev/shm 共享內存
Docker 預設只給 64MB，導致瀏覽器頁面崩潰

解決:
--shm-size=2gb  # 增加到 2GB
或
--tmpfs /dev/shm:rw,nosuid,nodev,noexec,relatime,size=2g
```

### 3. Seccomp 配置

更安全的方式（而非完全禁用）：

```json
// seccomp-profile.json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    {
      "names": ["clone", "unshare", "setns"],
      "action": "SCMP_ACT_ALLOW"
    }
  ]
}
```

```bash
docker run --security-opt seccomp=seccomp-profile.json ...
```

---

## 常見問題排查

### Q1: 瀏覽器啟動失敗 "Target closed"
```
原因: 內存不足或 shm-size 太小
解決: --shm-size=2gb --memory=4g
```

### Q2: "Running as root without --no-sandbox"
```
原因: Docker 中以 root 運行 Chromium
解決: launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] })
```

### Q3: 字體顯示問題（中文亂碼）
```dockerfile
# 安裝中文字體
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    fonts-wqy-microhei
```

### Q4: 時區問題
```dockerfile
ENV TZ=Asia/Hong_Kong
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
```

---

## 推薦配置總結

```yaml
# docker-compose.yml (生產環境)
version: '3.8'

services:
  odds-collector:
    build:
      context: .
      dockerfile: docker/odds-collector/Dockerfile
    environment:
      - RACE_DATE=${RACE_DATE}
      - VENUE=${VENUE}
      - API_BASE=http://api:3001
      - TZ=Asia/Hong_Kong
    
    # Chromium 必需權限
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined
    
    # 內存配置
    shm_size: '2gb'
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    
    # 自動重啟策略
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "pgrep", "-f", "odds_collector"]
      interval: 30s
      timeout: 10s
      retries: 3
    
    # 只在賽事日啟動
    profiles: ["race-day"]
```

```javascript
// scrapers/odds_collector.js (Docker 優化版)
const browser = await chromium.launch({
  headless: true,
  args: [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-web-security',
    '--disable-features=IsolateOrigins,site-per-process',
    '--disable-blink-features=AutomationControlled',  // 隱藏自動化標記
  ],
  // 限制資源使用
  dumpio: true,  // 輸出日誌便於調試
});

// 限制頁面數量防止內存洩漏
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  deviceScaleFactor: 1,
});
```

---

## 結論

✅ **Docker 中運行 Chromium 完全可行**

**關鍵要點**:
1. 使用官方 `mcr.microsoft.com/playwright` image 或安裝 Chromium
2. **必須**禁用沙盒 (`--no-sandbox`)
3. **必須**增加共享內存 (`--shm-size=2gb`)
4. 預留足夠內存 (4GB+ for odds-collector)
5. 考慮使用 `--cap-add=SYS_ADMIN` 或自定義 seccomp

**推薦**: 方案一（官方 Playwright Image）最穩定，方案二（Alpine）體積更小但配置更複雜。
