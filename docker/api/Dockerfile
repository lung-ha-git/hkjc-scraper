# API 服務 Dockerfile (Node.js Server)
FROM node:20-slim AS base

# 安裝 Python 和系統依賴
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 設置工作目錄
WORKDIR /app

# 複製 package.json 並安裝 Node 依賴
COPY web-app/package*.json ./
RUN npm install

# 創建 Python 虛擬環境
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 複製並安裝 Python 依賴
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# 複製應用代碼
COPY web-app/server ./web-app/server
COPY web-app/src ./web-app/src
COPY web-app/public ./web-app/public
COPY web-app/index.html ./
COPY web-app/vite.config.js ./
# 複製前端構建產物（如果存在）
RUN if [ -d web-app/dist ]; then cp -r web-app/dist ./dist; fi

# 創建必要的目錄
RUN mkdir -p logs data models scrapers

# 暴露端口
EXPOSE 3001

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:3001/health || exit 1

# 啟動命令
CMD ["node", "web-app/server/index.cjs"]
