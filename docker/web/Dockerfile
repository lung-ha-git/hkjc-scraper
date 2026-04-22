# Web 前端 Dockerfile (React + Vite)
FROM node:20-alpine AS builder

WORKDIR /app

# 複製 package.json
COPY package*.json ./
RUN npm ci

# 複製源代碼並構建
COPY . .
RUN npm run build

# 生產環境使用 Nginx
FROM nginx:alpine

# 安裝 curl 用於健康檢查
RUN apk add --no-cache curl

# 複製自定義 nginx 配置（包含 /api proxy）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 複製構建產物
COPY --from=builder /app/dist /usr/share/nginx/html
# 複製額外的靜態頁面 (logs.html)
COPY --from=builder /app/public/logs.html /usr/share/nginx/html/logs.html
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chmod -R 755 /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
