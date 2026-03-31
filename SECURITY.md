# Docker 安全指南

## ⚠️ 重要安全提醒

### 1. 環境變量與密碼

**必須在生產環境前完成：**
- 複製 `.env.example` 為 `.env`
- **更改所有默認密碼** (`MONGODB_ROOT_PASSWORD`, `MONGODB_APP_PASSWORD`)
- 使用強密碼（建議：16+ 字符，包含大小寫、數字、特殊符號）
- 不要將 `.env` 文件提交到 Git（已包含在 .dockerignore 和 .gitignore）

### 2. 密碼存儲位置

| 文件 | 用途 | 注意事項 |
|------|------|----------|
| `.env` | 環境變量 | 本地使用，不要上傳 |
| `docker-compose.yml` | 服務配置 | 使用 `${VAR:-default}` 語法，默認值僅供開發 |
| `docker/mongodb/init.js` | DB 初始化 | 從環境變量讀取密碼 |

### 3. 生產環境檢查清單

- [ ] 更改所有默認密碼
- [ ] 禁用 MongoDB 遠程訪問（如不需要）
- [ ] 配置 SSL/TLS 證書
- [ ] 設置防火牆規則
- [ ] 啟用日誌監控
- [ ] 定期備份數據

### 4. 開發 vs 生產

| 環境 | 配置 |
|------|------|
| 開發 | 可以使用默認值，localhost 訪問 |
| 生產 | **必須** 更改密碼，啟用 SSL，限制訪問 |

### 5. 快速啟動（開發環境）

```bash
# 1. 複製環境文件
cp .env.example .env

# 2. 開發環境可保持默認值，生產環境必須修改！
# 編輯 .env 文件

# 3. 啟動服務
docker-compose up -d
```

## 相關文件

- `.env.example` - 環境變量模板
- `.dockerignore` - Docker 構建忽略規則
- `docker/mongodb/init.js` - 數據庫初始化腳本
