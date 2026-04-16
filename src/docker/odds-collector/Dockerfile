# Odds Collector Dockerfile (Playwright/Chromium)
FROM mcr.microsoft.com/playwright:v1.41.0-jammy

WORKDIR /app

# 安裝 Node.js 20 (官方 Playwright image 使用 Node 18)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Python 和 pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# 創建 Python 虛擬環境
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 複製並安裝 Python 依賴
COPY src/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt playwright

# 複製 Node.js 依賴
COPY src/scrapers/package*.json ./scrapers/
RUN cd scrapers && npm install

# 複製應用代碼
COPY src/scrapers ./scrapers
COPY src/config ./config

# 安裝 Chromium（Playwright 官方鏡像可能不包含瀏覽器）
RUN npx playwright install chromium --with-deps 2>&1 | tail -5 || \
    npx playwright install chromium 2>&1 | tail -5

# 設置時區
ENV TZ=Asia/Hong_Kong
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 環境變量
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1
ENV MONGODB_URI=mongodb://admin:changeme@mongodb:27017/horse_racing?authSource=admin
ENV API_BASE=http://api:3001
ENV DB_NAME=horse_racing

# 保持 root 運行（pwuser 對 /app 無寫入權限）
# 默認命令
CMD ["node", "scrapers/odds_collector.js"]
