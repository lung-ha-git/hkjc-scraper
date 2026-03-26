/**
 * HKJC Live Odds Collector - Fresh Browser Per Cycle (~2s for 10 races)
 * 
 * Each scrape cycle launches a fresh Chrome → HKJC sees new session → no rate-limit
 * Broadcasts via WebSocket + MongoDB persistence
 * 
 * Usage:
 *   node odds_collector.js [date] [venue] [--continuous] [--interval N]
 *   node odds_collector.js 2026-03-22 ST --continuous --interval 10000
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/';
const DB_NAME = process.env.MONGODB_DATABASE || 'horse_racing';
const API_BASE = process.env.API_BASE || 'http://localhost:3001';

function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

// ─── Intercept GraphQL response ───────────────────────────────────────────────
async function fetchRaceOdds(page, date, venue, raceNo) {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      page.removeListener('response', responseHandler);
      resolve(null);
    }, 8000);

    const responseHandler = async (response) => {
      const url = response.url();
      if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
      try {
        const body = await response.text();
        if (!body.includes('"pmPools"') || !body.includes('"oddsNodes"')) return;
        const json = JSON.parse(body);
        if (!json?.data?.raceMeetings?.[0]?.pmPools) return;
        clearTimeout(timeout);
        page.removeListener('response', responseHandler);
        resolve(json);
      } catch (e) {}
    };

    page.on('response', responseHandler);
    page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/${raceNo}`, {
      waitUntil: 'domcontentloaded',
      timeout: 10000
    }).catch(() => {});
  });
}

// ─── Parse odds from GraphQL response ────────────────────────────────────────
function parseOdds(data) {
  if (!data?.data?.raceMeetings?.[0]?.pmPools) return null;
  const result = { win: {}, place: {} };
  data.data.raceMeetings[0].pmPools.forEach(pool => {
    const target = pool.oddsType === 'WIN' ? result.win
                 : pool.oddsType === 'PLA' ? result.place
                 : null;
    if (!target) return;
    pool.oddsNodes?.forEach(node => {
      target[node.combString] = parseFloat(node.oddsValue);
    });
  });
  return result;
}

// ─── Scrape all races using fresh browser ─────────────────────────────────────
async function scrapeAllRaces(date, venue, races) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();

    // Warm up session (new browser = new session = fast, no rate-limit)
    await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    });
    await page.waitForTimeout(2000);

    const results = [];
    for (const raceNo of races) {
      process.stdout.write(`  Race ${raceNo}... `);
      const data = await fetchRaceOdds(page, date, venue, raceNo);
      if (!data) { console.log('❌ no data'); continue; }

      const odds = parseOdds(data);
      if (!odds) { console.log('❌ parse failed'); continue; }

      const winKeys = Object.keys(odds.win);
      const plaKeys = Object.keys(odds.place);
      if (winKeys.length === 0 && plaKeys.length === 0) { console.log('❌ empty'); continue; }

      const raceId = buildRaceId(date, venue, raceNo);
      const normalizeKeys = (obj) => {
        const out = {};
        for (const [k, v] of Object.entries(obj)) out[Number(k)] = v;
        return out;
      };

      results.push({
        race_id: raceId, date, venue,
        race_no: parseInt(raceNo),
        win: normalizeKeys(odds.win),
        place: normalizeKeys(odds.place),
        scraped_at: new Date()
      });

      const winTop = Object.entries(odds.win).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(',');
      const plaTop = Object.entries(odds.place).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(',');
      console.log(`✅ WIN [${winTop}] PLA [${plaTop}]`);
    }

    await browser.close();
    return results;
  } catch (e) {
    await browser.close();
    throw e;
  }
}

// ─── MongoDB save ──────────────────────────────────────────────────────────────
async function saveToMongoDB(docs) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const collection = client.db(DB_NAME).collection('live_odds');
    const result = await collection.insertMany(docs.map(d => ({
      ...d,
      scraped_at: new Date()
    })));
    return result.insertedCount;
  } finally {
    await client.close();
  }
}

// ─── Broadcast snapshot to WebSocket server ───────────────────────────────────
async function broadcastSnapshot(raceId, odds) {
  try {
    const normalizedOdds = {};
    for (const [h, v] of Object.entries(odds)) {
      normalizedOdds[Number(h)] = v;
    }
    await fetch(`${API_BASE}/api/odds/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId, odds: normalizedOdds })
    });
  } catch (e) { /* silent */ }
}

// ─── Batch broadcast all races in one request ───────────────────────────────────
async function broadcastBatch(races) {
  if (races.length === 0) return;
  try {
    const body = races.map(race => ({
      race_id: race.race_id,
      odds: Object.fromEntries(
        Object.entries(race.odds || { win: race.win, place: race.place })
          .map(([h, v]) => [Number(h), v])
      )
    }));
    await fetch(`${API_BASE}/api/odds/batch-snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ races: body })
    });
  } catch (e) { /* silent */ }
}

// ─── Session tracking ────────────────────────────────────────────────────────
async function sessionStart(raceId) {
  try {
    await fetch(`${API_BASE}/api/odds/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId })
    });
  } catch (e) { /* silent */ }
}

async function sessionEnd(raceId) {
  try {
    await fetch(`${API_BASE}/api/odds/session/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId })
    });
  } catch (e) { /* silent */ }
}

// ─── Continuous collector loop ───────────────────────────────────────────────────
async function runCollector(date, venue, races, intervalMs = 10000) {
  console.log(`\n🚀 HKJC Odds Collector (Fresh Browser Per Cycle) starting...`);
  console.log(`📅 ${date} ${venue} | 🏃 Races: ${races.join(', ')} | ⏱️  Interval: ${intervalMs}ms\n`);

  // Register session start for each race
  for (const raceNo of races) {
    const raceId = buildRaceId(date, venue, raceNo);
    await sessionStart(raceId);
  }

  // Graceful shutdown: record session end
  const shutdown = async () => {
    console.log('\n🛑 Shutting down... recording session end');
    for (const raceNo of races) {
      const raceId = buildRaceId(date, venue, raceNo);
      await sessionEnd(raceId);
    }
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  const runOnce = async () => {
    const ts = new Date().toLocaleTimeString('en-GB');
    const startTime = Date.now();
    try {
      const results = await scrapeAllRaces(date, venue, races);
      const elapsed = Date.now() - startTime;

      if (results.length === 0) {
        console.error(`[${ts}] ❌ All races failed`);
        return false;
      }

      console.log(`\n[${ts}] ⏱️  Scraped ${results.length}/${races.length} races in ${elapsed}ms`);

      try {
        const saved = await saveToMongoDB(results);
        console.log(`[${ts}] 💾 MongoDB: ${saved} docs`);
      } catch (e) {
        console.error(`[${ts}] ⚠️  MongoDB: ${e.message}`);
      }

      // Batch broadcast all races in one request
      await broadcastBatch(results);
      console.log(`[${ts}] 📡 Batch broadcast → ${results.length} races`);

      return true;
    } catch (e) {
      console.error(`[${ts}] ❌ Error: ${e.message}`);
      return false;
    }
  };

  let success = await runOnce();
  let failures = 0;

  const scheduleNext = () => {
    const delay = success ? intervalMs : Math.min(intervalMs * 2, 60000);
    return setTimeout(async () => {
      success = await runOnce();
      failures = success ? 0 : failures + 1;
      scheduleNext();
    }, delay);
  };

  return scheduleNext();
}

// ─── One-shot mode ─────────────────────────────────────────────────────────────
async function runOnce(date, venue, races) {
  console.log(`\n🎯 One-shot: ${date} ${venue} races [${races.join(', ')}]\n`);
  const startTime = Date.now();
  const results = await scrapeAllRaces(date, venue, races);
  const elapsed = Date.now() - startTime;

  if (results.length > 0) {
    console.log(`\n⏱️  Done in ${elapsed}ms | 💾 Saving ${results.length} races...`);
    await saveToMongoDB(results);
    await broadcastBatch(results);
    console.log(`  📡 Batch broadcast → ${results.length} races\n✅ Done!\n`);
  } else {
    console.log('\n❌ No data.\n');
  }
}

// ─── CLI ───────────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const date = args[0] || '2026-03-22';
const venue = args[1] || 'ST';
const continuous = args.includes('--continuous');
const intervalArg = args.indexOf('--interval');
const intervalMs = intervalArg >= 0 ? parseInt(args[intervalArg + 1]) : 10000;
const racesArg = args.indexOf('--races');
const raceList = racesArg >= 0 ? args[racesArg + 1].split(',') : ['1','2','3','4','5','6','7','8','9','10'];

if (continuous) {
  runCollector(date, venue, raceList, intervalMs);
} else {
  runOnce(date, venue, raceList);
}
