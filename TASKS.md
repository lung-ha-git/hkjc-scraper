# HKJC Project — Feature Tasks

> 每個 feature 拆成 sub-tasks，方便一個個完成

---

## FEAT-009: Webapp Mobile UI — Compact Unified Table 🔴 HIGH ✅ DONE

**目標**: Racecard + Odds + Predictions 整合成一個 mobile-friendly compact table

### Sub-tasks

- [ ] **9.1** Audit current App.jsx layout — 了解現有 3-column 架構
  - **Test**: 瀏覽器 DevTools mobile 模式 (< 768px) 截圖記錄現狀
- [ ] **9.2** 研究 odds API response 格式 — 確認 racecard entries 包含哂咩 fields
  - **Test**: `curl /api/racecards` 輸出結構
- [ ] **9.3** 設計 unified table schema — 馬號/馬名/WIN/PLACE/信心指數/預測 rank
  - **Test**: 人工對照 mock data 確認各 column 有數值
- [ ] **9.4** 實現 unified table component (mobile-first)
  - **Test**: `npm run build` 無 error，`curl /` 正常 serve
- [ ] **9.5** Desktop layout: 保持 3-column or 改 2-column
  - **Test**: Desktop (≥1200px) 截圖確認 layout
- [ ] **9.6** 測試 mobile viewport (< 768px)
  - **Test**: DevTools mobile 模式，確認 unified table 顯示，3-column 隱藏
- [ ] **9.7** 移除/替換現有 OddsPanel component
  - **Test**: Desktop + Mobile 兩種mode 都正常，console 無 red error

**參考**: `web-app/src/App.jsx`, `web-app/src/components/`

---

## FEAT-010: Webapp UX — Clear on Race Switch ✅ DONE

> ✅ **DONE** `94e97d50` — clears racecard + predictions + odds on race switch

### Sub-tasks

- [x] **10.1** Identify where state lives ✅
- [x] **10.2** Reset oddsData/oddsHistory when raceId changes ✅
- [x] **10.3** Clear racecard + predictions on race change ✅
- [x] **10.4** Test rapid race switching ✅ (manual: R1→R3→R5 確認無 stale data)

---

## FEAT-011: Webapp UX — Persist Selected Race on Refresh ✅ DONE

> ✅ **DONE** `c3b06ab8` — localStorage restore on fixtures load, persist on race change

### Sub-tasks

- [x] **11.1** Restore from localStorage on mount ✅
- [x] **11.2** Persist on race change ✅
- [x] **11.3** Handle missing/invalid stored value ✅
- [x] **11.4** Test: Refresh page, confirm race preserved ✅

---

## FEAT-001: Batch Broadcast — 10→1 Request ✅ DONE

> ✅ **DONE** `c3b06ab8` — batch endpoint + scraper update

### Sub-tasks

- [x] **1.1** Server: `POST /api/odds/batch-snapshot` endpoint ✅
- [x] **1.2** Server: Broadcast all races in one loop ✅
- [x] **1.3** Scraper: One fetch() call for all races ✅
- [x] **1.4** Test: `curl -X POST /api/odds/batch-snapshot` → `{"ok":1,"races_count":N}` ✅
- [x] **1.5** Test: Scraper logs "Batch broadcast → N races" ✅

---

## FEAT-006: Racecard vs Actual Entries Validation 🟡 MEDIUM

**目標**: 每日 workflow 比對 racecard_entries 同 odds page entries，標記差異

### Sub-tasks

- [ ] **6.1** 研究 odds GraphQL response — 找出 actual entries fields
  - **Test**: `node scrapers/odds_collector.js` 單場，log 完整 response 結構
- [ ] **6.2** 寫 script 比對 `racecard_entries` vs `odds_entries`
  - **Test**: MongoDB query 確認兩邊 horse_no 集合差異
- [ ] **6.3** 整合進 daily pipeline (Python)
  - **Test**: `python racecards.py 2026-03-22` 確認 output 有 mismatch 報告
- [ ] **6.4** Output 報告：新增/移除/替補馬匹
  - **Test**: 對照 HKJC 官網賽事資料驗證
- [ ] **6.5** Webapp 顯示 "馬匹有變動" warning
  - **Test**: Mobile + Desktop 確認 warning badge 出現

**技術**: Python (racecards.py), MongoDB

---

## FEAT-007: HKJC Odds Page Racecard API 🟡 MEDIUM

**目標**: 用 odds GraphQL response 取代/補充 racecards.py

### Sub-tasks

- [ ] **7.1** Inspect full odds GraphQL response structure
  - **Test**: Playwright intercept response，完整 JSON 存檔分析
- [ ] **7.2** 確認 HKJC odds page 有咩額外 data (draw, wt., etc.)
  - **Test**: 對照 racecards.py 現有 fields
- [ ] **7.3** 寫 prototype script 測試
  - **Test**: Script 輸出 racecard JSON，與現有 API `/api/racecards` 對比
- [ ] **7.4** 評估：係咪值得替換
  - **Test**: 比較 field coverage + scrape speed
- [ ] **7.5** 實現 (如值得)
  - **Test**: 新舊 API output diff 為空

**技術**: Playwright intercept, GraphQL response parsing

---

## FEAT-008: Odds Service Start/End Times 🟢 LOW ✅ DONE

**目標**: 顯示 odds scraper 為每場賽事的服務時間

### Sub-tasks

- [ ] **8.1** 設計 storage: MongoDB schema 或 separate collection
  - **Test**: MongoDB insert/read roundtrip
- [ ] **8.2** 改 odds_collector: 記錄首個/最後 scrape 時間
  - **Test**: 單次 scrape，MongoDB 確認 timestamp fields
- [ ] **8.3** Webapp: 顯示 "Odds: 9:00 AM – 12:30 PM"
  - **Test**: DevTools network tab 確認 WS emit 含 timestamps
- [ ] **8.4** End-to-end test
  - **Test**: Scraper 運行 10 分鐘，webapp 顯示正確時間範圍

**技術**: `odds_collector.js`, `useOddsSocket.js`, `index.cjs`

---

## FEAT-002: oddsCache TTL Cleanup 🟢 LOW

**目標**: Server `oddsCache` 無限增長 → 加上 TTL/LRU eviction

### Sub-tasks

- [ ] **2.1** 測量現有 cache 大小
  - **Test**: `Object.keys(oddsCache).length` log over 1 hour
- [ ] **2.2** 設計 TTL 或 max-races limit eviction
  - **Test**: Mock data 觸發 eviction，確認 old keys removed
- [ ] **2.3** 實現 cleanup
  - **Test**: `npm run build` + `npm run dev` 無 error
- [ ] **2.4** 長期運行確認無 memory leak
  - **Test**: Scraper 運行 24h，memory stable (no growth)

**技術**: `server/index.cjs` oddsCache

---

## FEAT-003: cloudflared launchd Auto-Restart 🟢 LOW

**目標**: cloudflared tunnel 加入 launchd plist

### Sub-tasks

- [ ] **3.1** 確認 cloudflared config path
  - **Test**: `cat ~/.cloudflared/config.yml`
- [ ] **3.2** 創建 plist: `com.fatlung.cloudflared.plist`
  - **Test**: `launchctl load/unload` 無 error
- [ ] **3.3** Verify auto-restart after crash
  - **Test**: `kill cloudflared PID`，確認自動重啟
- [ ] **3.4** Reboot test (manual)
  - **Test**: 重啟 Mac，確認 tunnel 自動連接

**技術**: `launchd`, `cloudflared`

---

## FEAT-004: Odds Drift Alert 🟢 LOW

**目標**: 馬匹 WIN odds 偏離 >X% 時通知

### Sub-tasks

- [ ] **4.1** 設計 drift threshold (e.g., >20%)
  - **Test**: 人手計算 2 個 timepoint 的 odds 變化%
- [ ] **4.2** 實現: compare current vs opening odds
  - **Test**: Mock data 觸發 alert，確認 threshold 計算正確
- [ ] **4.3** WebSocket emit `odds_drift` event
  - **Test**: `curl /api/odds/:raceId` 確認 event payload 格式
- [ ] **4.4** Webapp: 顯示 drift badge 或 notification
  - **Test**: DevTools WS frames 確認 drift event 收到
- [ ] **4.5** End-to-end test
  - **Test**: Scraper 實時運行，odds 變化 >20% 時 UI 顯示 alert

**技術**: `odds_collector.js`, `useOddsSocket.js`, UI notification

---

## FEAT-012: Hybrid Odds Scraper — Race-Aware Auto Start/Stop 🟡 MEDIUM

**目標**: Scraping 智能化 — 賽前有赔率先開始，賽後有結果就停止；Hybrid storage (change-only + periodic snapshot)

### Context
- **問題**: `odds_collector.js --continuous` 永遠 loop，hardcoded date，冇 start/stop logic
- **問題**: 每 10s 寫一次 `live_odds`，storage 快速膨脹（12k+ docs/day）
- **問題**: Sparkline 需要均勻時間間距，但 change-only 會導致空白

### Hybrid 設計

**Storage Strategy:**
1. **Change-only**: 只寫 odds 實際變動的記錄 (`live_odds_changes`)
2. **Periodic snapshot**: 每 30s 寫一次 full snapshot（確保 sparkline 有均勻間距）
3. **Initial snapshot**: 每次 scrape 開始 / reconnect 時寫 full snapshot

**Workflow:**
```
Racecard API 發布馬票
    ↓
Racecard 馬匹出現在 odds page（即時 detect 或 cron check）
    ↓ 依賴 FEAT-007 (Odds Page Racecard API)
Scraper 自動啟動（date/venue/race_no 動態）
    ↓
Change-based 寫入 live_odds_changes
+ 每 30s 寫入 periodic snapshot 到 live_odds
    ↓
Race 結果出爐（detect via HKJC results API 或 cron）
    ↓
Scraper 自動停止，寫入 final snapshot
```

### Sub-tasks

- [ ] **12.1** Detect race start: odds appear on HKJC odds page
  - **Trigger**: Cron job 或 FEAT-007 webhook 通知
  - **Test**: 馬票出 + odds page 有 data → scraper 啟動
  - **依賴**: FEAT-007 (Odds Racecard API)
- [ ] **12.2** Detect race end: results published on HKJC
  - **Trigger**: `racecards` collection `results_status: 'final'` 或 results page scrape
  - **Test**: 比賽完成後 scraper 收到停止信號
  - **依賴**: pipeline results scraper
- [ ] **12.3** 实现 change-based write (vs current time-series)
  - **Change**: `odds_collector.js` — compare prev vs current，only insert when diff
  - **Test**: Mock odds 固定值 → 0 inserts；odds 變動 → 1 insert
- [ ] **12.4** Add periodic snapshot (every 30s)
  - **Purpose**: 確保 sparkline 有均勻間距，唔會因為長穩定而出現空白
  - **Implementation**: `live_odds` collection，flag `is_periodic: true`
  - **Test**: 30s 後睇 MongoDB 有 periodic snapshot
- [ ] **12.5** 实现 dynamic race selection (remove hardcoded date/venue)
  - **Change**: `odds_collector.js` — args 變成 `date venue race_no`動態
  - **Change**: launchd plist — 變成 event-driven 而非 always-on
  - **Test**: API trigger scraper 跑指定 R1，唔跑其他場
- [ ] **12.6** API endpoint: `POST /api/scraper/start` + `POST /api/scraper/stop`
  - **Purpose**: Webapp / cron 觸發 scraper
  - **Test**: `curl -X POST /api/scraper/start -d '{"date":"2026-03-25","venue":"ST","race_no":"1"}'`
- [ ] **12.7** cleanup: archive/delete `live_odds` old records (>24h)
  - **Test**: `live_odds` 保持合理大小（每場 ~100 docs max）

**技術**: `odds_collector.js`, `index.cjs`, `launchd`, MongoDB

**相關**: FEAT-007 (Odds Racecard API), FEAT-008 (Start/End Times)

---

## Testing Guide

### 快速本地測試
```bash
# Build + serve
cd web-app && npm run build
curl http://localhost:3001/

# Mobile viewport test
# DevTools → Toggle device toolbar → iPhone 14 / 390x844

# API test
curl http://localhost:3001/api/fixtures
curl http://localhost:3001/api/racecards?date=2026-03-22
curl http://localhost:3001/api/odds/history/2026-03-22_ST_R1

# WebSocket test
node -e "const io=require('./node_modules/socket.io-client');const s=io('http://localhost:3001',{path:'/socket.io/'});s.on('connect',()=>{console.log('WS OK');s.disconnect();process.exit(0)})"
```

### Mobile Testing Checklist
- [ ] iPhone SE (375px) — 最小 viewport
- [ ] iPhone 14 (390px) — 主要 mobile
- [ ] iPad (768px) — tablet breakpoint
- [ ] Desktop 1440px — 確認 desktop layout 未受影响
- [ ] Console 無 red errors
- [ ] Network tab 無 failed requests
