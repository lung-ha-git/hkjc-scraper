# TASK-005: 設定 Cloudflare Tunnel (horse.fatlung.com)

**創建日期**: 2026-03-26  
**狀態**: 已驗證  
**執行人**: The_Brain / Dev_Alpha  
**優先級**: High  
**截止時間**: 盡快

---

## 任務描述

使用 Cloudflare Tunnel 將本地 HKJC 服務暴露到互聯網，域名為 `horse.fatlung.com`

## 當前服務狀態

| 服務 | 端口 | URL |
|------|------|-----|
| Web | 80 | http://localhost |
| API | 3001 | http://localhost:3001 |

## 目標

- **外部 URL**: https://horse.fatlung.com
- **API URL**: https://horse.fatlung.com/api

## 實作步驟

### 方案 A: Cloudflare Tunnel (推薦)

1. **安裝 cloudflared**
   ```bash
   # macOS
   brew install cloudflare/cloudflare/cloudflared
   
   # 或下載 binary
   curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64 -o /usr/local/bin/cloudflared
   chmod +x /usr/local/bin/cloudflared
   ```

2. **登入 Cloudflare**
   ```bash
   cloudflared tunnel login
   ```

3. **創建 Tunnel**
   ```bash
   cloudflared tunnel create hkjc-tunnel
   # 記下 tunnel ID
   ```

4. **配置 DNS**
   ```bash
   cloudflared tunnel route dns hkjc-tunnel horse.fatlung.com
   ```

5. **配置 cloudflared.yml**
   ```bash
   mkdir -p ~/.cloudflared
   cat > ~/.cloudflared/config.yml << EOF
   tunnel: <TUNNEL_ID>
   credentials-file: /root/.cloudflared/<TUNNEL_ID>.json
   
   ingress:
     - hostname: horse.fatlung.com
       service: http://localhost:80
     - service: http_status:404
   ```

6. **運行 Tunnel**
   ```bash
   # 直接運行
   cloudflared tunnel run hkjc-tunnel
   
   # 或作為服務運行
   cloudflared service install
   ```

### 方案 B: Docker Cloudflared

```yaml
# docker-compose.yml 添加
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: hkjc-cloudflared
  restart: unless-stopped
  command: tunnel run --token ${CLOUDFLARE_TUNNEL_TOKEN}
  profiles:
    - production
```

## 環境變量

在 `.env` 中添加：
```
CLOUDFLARE_TUNNEL_TOKEN=<your-tunnel-token>
```

## 驗證

完成後訪問：
- https://horse.fatlung.com (Web)
- https://horse.fatlung.com/api/health (API)

## 相關文檔

- Cloudflare Tunnel 文檔: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
