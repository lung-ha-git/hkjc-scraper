# HKJC Project — Feature Tasks

> 每個 feature 拆成 sub-tasks，方便一個個完成

---

## FEAT-009: Webapp Mobile UI — Compact Unified Table 🔴 HIGH

**目標**: Racecard + Odds + Predictions 整合成一個 mobile-friendly compact table

### Sub-tasks

- [ ] **9.1** Audit current App.jsx layout — 了解現有 3-column 架構
- [ ] **9.2** 研究 odds API response 格式 — 確認 racecard entries 包含哂咩 fields
- [ ] **9.3** 設計 unified table schema — 馬號/馬名/WIN/PLACE/信心指數/預測 rank
- [ ] **9.4** 實現 unified table component (mobile-first)
- [ ] **9.5** Desktop layout: 保持 3-column or 改 2-column
- [ ] **9.6** 測試 mobile viewport (< 768px)
- [ ] **9.7** 移除/替換現有 OddsPanel component

**參考**: `web-app/src/App.jsx`, `web-app/src/components/`

---

## FEAT-011: Webapp UX — Persist Selected Race on Refresh 🔴 HIGH

**目標**: Page refresh 時維持場次，唔回到 R1

### Sub-tasks

- [ ] **11.1** 在 App.jsx mount 時讀取 `localStorage.getItem('selectedRace')`
- [ ] **11.2** Race change 時寫入 `localStorage.setItem('selectedRace', raceId)`
- [ ] **11.3** Handle missing/invalid stored value gracefully (default to R1)

**技術**: React `useEffect` on mount, `localStorage`

---

## FEAT-006: Racecard vs Actual Entries Validation 🟡 MEDIUM

**目標**: 每日 workflow 比對 racecard_entries 同 odds page entries，標記差異

### Sub-tasks

- [ ] **6.1** 研究 odds GraphQL response — 找出 actual entries fields
- [ ] **6.2** 寫 script 比對 `racecard_entries` vs `odds_entries`
- [ ] **6.3** 整合進 daily pipeline (Python: racecards.py)
- [ ] **6.4** Output 報告：新增馬匹、移除馬匹、替補
- [ ] **6.5** UI 提示：webapp 顯示 "馬匹有變動" warning

**技術**: Python (racecards.py), MongoDB `racecard_entries` vs `live_odds`

---

## FEAT-010: Webapp UX — Clear on Race Switch 🟡 MEDIUM

**目標**: R1→R2 時清空舊 content，防止 stale data flash

### Sub-tasks

- [ ] **10.1** Identify where state lives (App.jsx vs individual components)
- [ ] **10.2** Reset oddsData/oddsHistory when raceId changes
- [ ] **10.3** Add "loading" indicator during race switch
- [ ] **10.4** Test rapid race switching (R1→R3→R5)

**技術**: React state reset on `raceId` dependency change

---

## FEAT-007: HKJC Odds Page Racecard API 🟡 MEDIUM

**目標**: 用 odds GraphQL response 取代/補充 racecards.py

### Sub-tasks

- [ ] **7.1** Inspect full odds GraphQL response structure — 找 racecard fields
- [ ] **7.2** 確認 HKJC odds page 有咩額外 data (draw, wt., etc.)
- [ ] **7.3** 寫 prototype script 測試
- [ ] **7.4** 評估：係咪值得替換現有 racecards.py
- [ ] **7.5** 實現 (如值得): 修改 pipeline 或新增 API endpoint

**技術**: Playwright intercept, GraphQL response parsing

---

## FEAT-008: Odds Service Start/End Times 🟢 LOW

**目標**: 顯示 odds scraper 為每場賽事的服務時間

### Sub-tasks

- [ ] **8.1** 設計 storage: MongoDB schema (新增 fields) 或 separate collection
- [ ] **8.2** 改 odds_collector: 記錄首個 scrape 時間
- [ ] **8.3** 實現 websocket emit when first/last scrape for a race
- [ ] **8.4** Webapp: 顯示 "Odds collected: 9:00 AM – 12:30 PM"

**技術**: `odds_collector.js`, `useOddsSocket.js`, `index.cjs`

---

## FEAT-001: Batch Broadcast — 10→1 Request 🟢 LOW

**目標**: odds_collector 每輪 10 races 140 個 fetch() → 1 個 batched request

### Sub-tasks

- [ ] **1.1** Server: 新增 `POST /api/odds/batch-snapshot` endpoint
- [ ] **1.2** Server: Broadcast all races' snapshots in one `io.to()` loop
- [ ] **1.3** Scraper: Collect all races' odds → one fetch() call
- [ ] **1.4** Test: 確認 WS clients 收到所有 races' snapshots

**技術**: `server/index.cjs`, `odds_collector.js`

---

## FEAT-002: oddsCache TTL Cleanup 🟢 LOW

**目標**: Server `oddsCache` 無限增長 → 加上 TTL/LRU eviction

### Sub-tasks

- [ ] **2.1** 測量: 現有 cache 大小 (`Object.keys(oddsCache).length`)
- [ ] **2.2** 設計: TTL (每場比賽 N 小時後過期) 或 max-races limit
- [ ] **2.3** 實現: `setInterval` cleanup 或每次 write 時 check
- [ ] **2.4** Test: 長期運行確認無 memory leak

**技術**: `server/index.cjs` oddsCache

---

## FEAT-003: cloudflared launchd Auto-Restart 🟢 LOW

**目標**: cloudflared tunnel 加入 launchd plist，開機自動重連

### Sub-tasks

- [ ] **3.1** 確認 cloudflared config path (`~/.cloudflared/config.yml`)
- [ ] **3.2** 創建 plist: `com.fatlung.cloudflared.plist`
- [ ] **3.3** Test: `launchctl load/unload`
- [ ] **3.4** Verify auto-restart after reboot (manual test)

**技術**: `launchd`, `cloudflared`

---

## FEAT-004: Odds Drift Alert 🟢 LOW

**目標**: 當馬匹 WIN odds 偏離開盤赔率 >X% 時通知

### Sub-tasks

- [ ] **4.1** 設計: 門檻值 (e.g., >20% drift)
- [ ] **4.2** 實現: `odds_collector.js` compare current vs opening odds
- [ ] **4.3** Alert 方式: WebSocket emit `odds_drift` event
- [ ] **4.4** Webapp: 顯示 drift badge 或 notification
- [ ] **4.5** 測試 with live data

**技術**: `odds_collector.js`, `useOddsSocket.js`, UI notification

---

## Task Management Tools

### VSCode Extensions to Consider
- **Todo Tree** — Shows all TODO/FIXME/X-TAG in sidebar
- **Task Manager** — Visual task board in VSCode
- **Project Manager** — Switch between project workspaces
- **Markdown All in One** — Better .md editing
- **Open in VSCode** — Workspace-level task files

### Alternative: Plain Text / Markdown
- Keep this `TASKS.md` as source of truth
- Check off items as completed
- Update `memory/YYYY-MM-DD.md` when done

### Alternative: Linear / Notion (External)
- 如果想要 web-based task board
- Linear: API-driven, fast keyboard shortcuts
- Notion: Flexible databases

### Recommendation
**VSCode Todo Tree + 本 `TASKS.md` file**

在 VSCode 安裝 **Todo Tree** extension，然後喺每個 sub-task 加上 tag:

```javascript
// TODO.9.1  Audit current App.jsx layout
// TODO.11.2 Race change 時寫入 localStorage
```

Todo Tree 會自動 crawl 所有檔案，喺 sidebar 顯示所有 tasks ✅
