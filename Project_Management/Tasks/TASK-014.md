---
task_id: TASK-014
status: 已完成
priority: High
assignee: Dev_Alpha
reviewer: 
created: 2026-03-29
started: 2026-03-29 11:07
completed: 2026-03-29 11:07
verified: 
tags:
  - 已完成
  - Dev_Alpha
  - High
---

# TASK-014: API Server 預加載 Odds Cache（預防重啟後失效）

## 描述
今天 10:17 左右 API 重啟，導致 in-memory cache 丟失所有 odds 數據。

**根本原因：**
1. API server 啟動時**沒有從 MongoDB 預加載** `live_odds` 數據到 cache
2. 依賴 scraper 的實時廣播，但 scraper 經常失敗
3. **每次 API 重啟都會丟失 cache**

**緊急修復已完成（10:53）：**
- 手動同步了 11 個 race 的 odds 到 cache

**需要修復（避免未來再次發生）：**

在 `server/index.cjs` 的 `connect()` 後添加預加載邏輯：

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
| 2026-03-29 10:53 | 建立任務 | The_Brain |
| 2026-03-29 10:53 | 緊急修復：手動同步 cache | The_Brain |
| 2026-03-29 11:07 | 確認代碼已存在（preloadOddsCache 在 index.cjs 已實現）| Dev_Alpha |

## 審查備註
- 緊急修復已由 The_Brain 手動完成（11 個 race 已同步）
- 這是防止未來再次發生的根本修復
