/**
 * HKJC Live Odds Collector - Fast + Fallback Hybrid
 * 
 * 1. Fast: session-reuse (1 browser, ~2s for 10 races)
 * 2. Fallback: fresh browser per race if blocked
 * 3. Broadcasts via WebSocket + MongoDB persistence
 * 
 * Usage:
 *   node odds_collector.js [date] [venue] [--continuous] [--interval N]
 *   node odds_collector.js 2026-03-22 ST --continuous --interval 10000
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');

const MONGODB_URI = 'mongodb://localhost:27017/';
const DB_NAME = 'hkjc_racing_dev';
const API_BASE = 'http://localhost:3001';

function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

// ─── Slow method: fresh browser per race (reliable, ~2s/race) ───────────────
async function fetchRaceOddsSlow(browser, date, venue, raceNo) {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => resolve(null), 8000);
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
    const page = browser.newPage ? null : null; // unused in this path
    // For slow method we create a fresh page inline
    resolve(null); // placeholder – real implementation below
  });
}

// ─── Parse GraphQL odds response → { win: {}, place: {} } ───────────────────
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

// ─── Fast method: intercept with listener attached before navigation ─────────
async function fetchRaceFast(page, date, venue, raceNo) {
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

// ─── MongoDB save ────────────────────────────────────────────────────────────
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

// ─── Broadcast to WebSocket server ───────────────────────────────────────────
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

// ─── Scrape one race using fast session-reuse ────────────────────────────────
async function scrapeFast(page, date, venue, raceNo) {
  const data = await fetchRaceFast(page, date, venue, raceNo);
  if (!data) return null;
  const odds = parseOdds(data);
  if (!odds) return null;
  // Check: did we get actual odds data?
  const winKeys = Object.keys(odds.win);
  const plaKeys = Object.keys(odds.place);
  if (winKeys.length === 0 && plaKeys.length === 0) return null;
  return odds;
}

// ─── Scrape one race using slow fresh-browser ────────────────────────────────
async function scrapeSlow(date, venue, raceNo) {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage();
    const data = await fetchRaceFast(page, date, venue, raceNo);
    if (!data) return null;
    const odds = parseOdds(data);
    return odds;
  } finally {
    await browser.close();
  }
}

// ─── Scrape all races: fast first, fallback slow for empty races ─────────────
async function scrapeAllRaces(date, venue, races) {
  console.log('🔐 Establishing session (fast mode)...');
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();
  
  // Warm up session (3s to avoid HKJC blocking sequential navigation)
  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });
  await page.waitForTimeout(3000);
  console.log('✅ Session ready\n');

  const results = [];
  const failedRaces = [];

  // Fast pass
  const startTime = Date.now();
  for (const raceNo of races) {
    process.stdout.write(`  Race ${raceNo} (fast)... `);
    const odds = await scrapeFast(page, date, venue, raceNo);
    if (odds) {
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
    } else {
      console.log(`⚠️  empty/blocked`);
      failedRaces.push(raceNo);
    }
  }
  await browser.close();

  // Fallback pass: slow fresh browser for blocked races
  if (failedRaces.length > 0) {
    console.log(`\n⚠️  Falling back (slow mode) for races: ${failedRaces.join(', ')}\n`);
    for (const raceNo of failedRaces) {
      process.stdout.write(`  Race ${raceNo} (slow)... `);
      const odds = await scrapeSlow(date, venue, raceNo);
      if (odds) {
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
        console.log(`✅ (recovered) WIN [${winTop}]`);
      } else {
        console.log(`❌ (failed)`);
      }
    }
  }

  const elapsed = Date.now() - startTime;
  console.log(`\n⏱️  Scraped ${results.length}/${races.length} races in ${elapsed}ms (fast+fallback)`);
  return results;
}

// ─── Continuous collector loop ────────────────────────────────────────────────
async function runCollector(date, venue, races, intervalMs = 10000) {
  console.log(`\n🚀 HKJC Odds Collector (Fast+Fallback) starting...`);
  console.log(`📅 ${date} ${venue} | 🏃 Races: ${races.join(', ')} | ⏱️  Interval: ${intervalMs}ms\n`);

  let isFirstRun = true;

  const runOnce = async () => {
    const timestamp = new Date().toLocaleTimeString('en-GB');
    try {
      const results = await scrapeAllRaces(date, venue, races);
      if (results.length === 0) {
        console.error(`[${timestamp}] ❌ All races failed`);
        return false;
      }

      // Save to MongoDB
      try {
        const saved = await saveToMongoDB(results);
        console.log(`[${timestamp}] 💾 MongoDB: ${saved} docs`);
      } catch (e) {
        console.error(`[${timestamp}] ⚠️  MongoDB: ${e.message}`);
      }

      // Broadcast to WebSocket
      for (const race of results) {
        await broadcastSnapshot(race.race_id, { win: race.win, place: race.place });
        console.log(`[${timestamp}] 📡 Broadcast → ${race.race_id}`);
      }

      isFirstRun = false;
      return true;
    } catch (e) {
      console.error(`[${timestamp}] ❌ Error: ${e.message}`);
      return false;
    }
  };

  // Run immediately, then on interval
  let success = await runOnce();
  let currentInterval = intervalMs;
  let failures = 0;

  const scheduleNext = () => {
    const delay = success ? currentInterval : Math.min(currentInterval * 2, 60000);
    return setTimeout(async () => {
      success = await runOnce();
      failures = success ? 0 : failures + 1;
      currentInterval = success ? intervalMs : Math.min(intervalMs * Math.pow(2, failures), 120000);
      scheduleNext();
    }, delay);
  };

  return scheduleNext();
}

// ─── One-shot mode ────────────────────────────────────────────────────────────
async function runOnce(date, venue, races) {
  console.log(`\n🎯 One-shot mode: ${date} ${venue} races [${races.join(', ')}]\n`);
  const results = await scrapeAllRaces(date, venue, races);
  if (results.length > 0) {
    console.log(`\n💾 Saving ${results.length} races to MongoDB...`);
    await saveToMongoDB(results);
    console.log(`\n📡 Broadcasting snapshots...`);
    for (const race of results) {
      await broadcastSnapshot(race.race_id, { win: race.win, place: race.place });
      console.log(`  📡 ${race.race_id}`);
    }
    console.log('\n✅ Done!\n');
  } else {
    console.log('\n❌ No data scraped.\n');
  }
}

// ─── CLI ─────────────────────────────────────────────────────────────────────
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
