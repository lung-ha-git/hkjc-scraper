# HKJC Data Sources

## 主要數據源 (由用戶提供)

### 1. 馬匹選擇頁面 (切入點)
- **URL**: https://racing.hkjc.com/zh-hk/local/information/selecthorse
- **內容**: 二字馬、三字馬資料
- **用途**: 獲取馬匹基本資訊

### 2. 練馬師排名
- **URL**: https://racing.hkjc.com/zh-hk/local/info/trainer-ranking
- **參數**: 
  - `season=Current` (當前 season)
  - `view=Numbers` (數字 view)
  - `racecourse=ALL` (所有馬場)
- **內容**: 練馬師勝利場數、排名等

### 3. 騎師排名
- **URL**: https://racing.hkjc.com/zh-hk/local/info/jockey-ranking
- **參數**: 
  - `season=Current`
  - `view=Numbers`
  - `racecourse=ALL`
- **內容**: 騎師勝利場數、排名等

### 4. 歷史賽果
- **URL**: https://racing.hkjc.com/zh-hk/local/information/localresults
- **內容**: 過往賽事結果
- **用途**: 主要賽果數據源

---

## Playwright 抓取策略

### 頁面特點
- 全部係 `/zh-hk/` 中文介面
- 使用 JavaScript 動態加載
- 需要等待元素出現

### 抓取步驟
1. 用 Playwright 打開頁面
2. 等待 JavaScript 渲染完成
3. 提取 table/element 數據
4. 關閉瀏覽器

### 待安裝
```bash
pip install playwright
playwright install chromium
```

---

*記錄時間: 2026-03-08*
