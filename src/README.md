# HKJC Horse Racing Data Analysis Project

## 項目簡介
香港賽馬會 (HKJC) 賽馬數據分析與預測系統

## 技術棧
- Python 3.10+
- MongoDB (數據庫)
- Scrapy/BeautifulSoup (數據抓取)
- Pandas (數據處理)
- XGBoost/LightGBM (AI 預測)
- FastAPI (API)
- React (前端)

## 項目結構
```
hkjc_project/
├── src/
│   ├── crawler/         # 數據抓取模組
│   │   └── hkjc_scraper.py
│   ├── database/       # 數據庫連接
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── setup_db.py
│   ├── etl/           # 數據清洗
│   │   └── pipeline.py
│   └── api/           # FastAPI (待開發)
├── config/             # 配置文件
│   ├── settings.py
│   └── .env.example
├── tests/              # 測試
│   └── test_scraper.py
├── data/              # 數據存儲
│   ├── raw/           # 原始數據
│   └── processed/     # 處理後數據
├── notebooks/         # 分析筆記
│   └── exploration.ipynb
└── requirements.txt    # 依賴
```

## 快速開始

### 1. 安裝依賴
```bash
cd hkjc_project
pip install -r requirements.txt
```

### 2. 設置 MongoDB
```bash
# 安裝 MongoDB Community Edition
# macOS: brew tap mongodb/brew && brew install mongodb-community
# 啟動: mongod --config /opt/homebrew/etc/mongod.conf
```

### 3. 初始化數據庫
```bash
python -m src.database.setup_db
```

### 4. 測試抓取
```bash
python -m src.crawler.hkjc_scraper
```

## 數據模型

### Races Collection
```json
{
  "race_id": "20260301_R1",
  "date": "2026-03-01",
  "venue": "HV",
  "race_no": 1,
  "distance": 1200,
  "course": "TURF",
  "track_condition": "GF",
  "runners": [...]
}
```

## 開發日誌
- 2026-03-07: 項目初始化，完成基本結構
- 2026-03-08: Phase 1 開發 - 數據抓取與數據庫集成

## License
僅供研究用途
