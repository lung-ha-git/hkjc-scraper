# TASK-008: 將 odds-collector service 加入 Docker 環境

**創建日期**: 2026-03-27  
**狀態**: 已完成  
**執行人**: Dev_Alpha → The_Brain（代完成）  
**優先級**: High

---

## 背景

`odds-collector` service 在 `docker-compose.yml` 中已定義但**從未被啟動**（無容器運行）。同時 `docker/odds-collector/Dockerfile` 引用了不存在的 `src/scrapers/package.json`。

### 當前狀態

```bash
docker ps  # 顯示: api, mongodb, pipeline, web
           # 缺少: odds-collector
```

### docker-compose.yml 中的定義（第 83-115 行）
- service 名: `odds-collector`
- Dockerfile: `docker/odds-collector/Dockerfile`
- 依賴: `mongodb`, `api`
- 用途: Playwright/Chromium 爬取賽馬赔率數據

## 修復步驟

### 1. 創建 `src/scrapers/package.json`

Odds collector 需要 Node.js dependencies，創建：

```json
{
  "name": "hkjc-odds-collector",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node odds_collector.js"
  },
  "dependencies": {
    "playwright": "^1.41.0",
    "axios": "^1.6.2",
    "dotenv": "^17.3.1"
  }
}
```

### 2. 檢查 `odds_collector.js` 是否完整

確認 `src/scrapers/odds_collector.js` 存在且需要 `package.json` 中的 dependencies。

### 3. 構建並啟動 odds-collector

```bash
cd Projects/HKJC
docker compose build odds-collector
docker compose up -d odds-collector
```

### 4. 驗證

```bash
docker ps  # 應顯示 hkjc-odds-collector
docker logs hkjc-odds-collector --tail 20  # 檢查啟動日誌
```

## 驗收標準

- [x] `src/scrapers/package.json` 已創建
- [x] `docker compose build odds-collector` 成功（無錯誤）
- [x] `docker compose up -d odds-collector` 成功啟動
- [x] `docker ps` 顯示 5 個容器（api, mongodb, odds-collector, pipeline, web）
- [x] `docker logs hkjc-odds-collector` 無崩潰錯誤
- [x] 通知 The_Tester 進行功能測試

## 參考文件

- `docker-compose.yml` (service definition)
- `docker/odds-collector/Dockerfile`
- `src/scrapers/odds_collector.js`

---

## 完成記錄

- 2026-03-27：Dev_Alpha 只做了分析，The_Brain 代為完成所有實際工作
- 發現額外問題：`src/scrapers/package.json` 缺失、`odds_collector.js` 使用 localhost、`channel: 'chrome'` 需要 Google Chrome
- 全部已修復並驗證：容器啟動成功，exit code 0
