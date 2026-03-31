# Daily Pipeline Dockerfile (Python + Cron)
FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴 (Playwright + Cron 需要)
RUN apt-get update && apt-get install -y \
    git \
    wget \
    gnupg \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libxdamage1 \
    libxfixes3 \
    libx11-xcb1 \
    libxcb1 \
    cron \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements 並安裝
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright 瀏覽器
RUN playwright install chromium

# 複製源代碼
COPY src/ .

# 設置 crontab (每天早上 6 點運行)
# 注意：系統 crontab (/etc/cron.d/) 需要 username 欄位，這裡使用 user crontab
RUN echo 'PATH=/usr/local/bin:/usr/bin:/bin\n0 6 * * * cd /app && /usr/local/bin/python3 daily_pipeline.py >> /app/logs/pipeline_cron.log 2>&1' | crontab -
# 同時創建系統 crontab 備份（正確格式，防止重建後復發）
RUN echo "PATH=/usr/local/bin:/usr/bin:/bin\n0 6 * * * root cd /app && /usr/local/bin/python3 daily_pipeline.py >> /app/logs/pipeline_cron.log 2>&1" > /etc/cron.d/hkjc-pipeline && chmod 0644 /etc/cron.d/hkjc-pipeline

# 創建日誌目錄
RUN mkdir -p /app/logs

# 設置 Python 路徑
ENV PYTHONPATH=/app
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# 啟動 cron 並運行 pipeline
CMD ["sh", "-c", "cron && tail -f /dev/null"]
