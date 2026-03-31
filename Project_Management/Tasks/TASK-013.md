---
task_id: TASK-013
status: 已驗證
priority: High
assignee: Dev_Alpha
reviewer: The_Debugger
created: 2026-03-29
started: 2026-03-29
completed: 2026-03-29
verified: 2026-03-29
tags:
  - 已驗證
  - Dev_Alpha
  - High
---

# TASK-013: API Server 啟動時預加載 Odds Cache

## 描述
API Server (hkjc-api) 的 in-memory cache 在重啟後是空的，導致：
- `/api/odds/:raceId` 返回空的 odds（只有 `updated_at`，沒有 `win/place`）
- WebSocket 也無法廣播正確的 odds 數據
- 用戶看到 webapp 沒有 odds

**根本原因：**
1. API server 啟動時沒有從 MongoDB 預加載 `live_odds` 數據到 cache
2. 依賴 scraper 的實時廣播，但 scraper 經常失敗

**修復方案：**
在 `server/index.cjs` 的 `connect()` 成功後，添加預加載邏輯：

```javascript
// 在 connect() 的 .then() 中添加
async function preloadOddsCache() {
  const races = await db.collection('live_odds').aggregate([
    { $sort: { scraped_at: -1 } },
    { $group: { _id: '$race_id', latest: { $first: '$$ROOT' } } }
  ]).toArray();
  
  const now = Date.now();
  for (const race of races) {
    const cached = {};
    for (const [hk, win] of Object.entries(race.latest.win || {})) {
      cached[Number(hk)] = { 
        win, 
        place: race.latest.place?.[hk], 
        updated_at: now 
      };
    }
    oddsCache[race._id] = cached;
  }
  console.log(`[preload] Loaded ${races.length} races into cache`);
}
await preloadOddsCache();
```

## 驗收標準
1. ✅ API server 重啟後，cache 包含所有最新 odds
2. ✅ `/api/odds/:raceId` 返回完整的 `{ win, place, updated_at }` 數據
3. ✅ WebSocket client 連接時能收到正確的 odds snapshot
4. ✅ 無需手動同步，webapp 刷新即可顯示 odds

## 交付文件
- `src/web-app/server/index.cjs`（修復後）

## 日誌
| 時間 | 動作 | 執行人 |
|------|------|--------|
| 2026-03-29 | 建立任務 | The_Brain |

## 審查備註
- 發現人：The_Debugger
- 參考：已驗證的同步腳本可正常工作（見下方命令）
- 注意：只加載每個 race 的最新一筆記錄
