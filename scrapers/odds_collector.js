/**
 * HKJC Live Odds Collector
 * 
 * Scrapes odds every 5 seconds and broadcasts via WebSocket.
 * Also writes to MongoDB for persistence.
 * 
 * Usage:
 *   node odds_collector.js [date] [venue]
 *   node odds_collector.js 2026-03-22 ST
 *   node odds_collector.js 2026-03-22 ST --continuous
 *   node odds_collector.js 2026-03-22 ST --races 1,2,3 --interval 5000
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');

const MONGODB_URI = 'mongodb://localhost:27017/';
const DB_NAME = 'hkjc_racing_dev';
const API_BASE = 'http://localhost:3001';

// race_id format: "YYYY-MM-DD_VENUE_RNo" e.g. "2026-03-22_ST_R7"
function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

/**
 * Intercept GraphQL response to get odds.
 * Listener is attached BEFORE navigation (listener-first pattern).
 */
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

/**
 * Parse odds from GraphQL response.
 * Returns { win: { "01": 3.5, ... }, place: { "01": 1.23, ... } }
 */
function parseOdds(data) {
  if (!data?.data?.raceMeetings?.[0]?.pmPools) return null;

  const meeting = data.data.raceMeetings[0];
  const result = { win: {}, place: {} };

  meeting.pmPools.forEach(pool => {
    const target = pool.oddsType === 'WIN' ? result.win
                 : pool.oddsType === 'PLA' ? result.place
                 : null;
    if (!target) return;

    pool.oddsNodes?.forEach(node => {
      // combString is "01", "02", etc.
      target[node.combString] = parseFloat(node.oddsValue);
    });
  });

  return result;
}

/**
 * Broadcast single odds update to WebSocket server
 */
async function broadcastOddsUpdate(raceId, horseNo, win, place) {
  try {
    // Normalize horseNo to number (odds scraper returns "01", "02" strings)
    await fetch(`${API_BASE}/api/odds/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId, horse_no: Number(horseNo), win, place })
    });
  } catch (e) {
    // Silent failure to not block scraping
  }
}

/**
 * Broadcast full snapshot to WebSocket server
 */
async function broadcastSnapshot(raceId, odds) {
  try {
    // Normalize all horse_no keys to numbers (keys come as "01", "02" strings from scraper)
    const normalizedOdds = {};
    for (const [h, v] of Object.entries(odds)) {
      normalizedOdds[Number(h)] = v;
    }
    await fetch(`${API_BASE}/api/odds/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId, odds: normalizedOdds })
    });
  } catch (e) {
    // Silent failure
  }
}

/**
 * Save to MongoDB
 */
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

/**
 * Scrape all races one by one using the established browser session.
 * Each race gets its own navigation + listener cycle.
 */
async function scrapeAllRaces(browser, date, venue, races) {
  const page = await browser.newPage();

  // Establish session first (visit race 1)
  console.log('🔐 Establishing session...');
  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });
  await page.waitForTimeout(3000);
  console.log('✅ Session ready\n');

  const results = [];

  // Fetch each race sequentially
  for (const raceNo of races) {
    process.stdout.write(`  Race ${raceNo}... `);

    const data = await fetchRaceOdds(page, date, venue, raceNo);

    if (!data) {
      console.log('❌ no data');
      continue;
    }

    const odds = parseOdds(data);
    if (!odds || (Object.keys(odds.win).length === 0 && Object.keys(odds.place).length === 0)) {
      console.log('❌ empty odds');
      continue;
    }

    const raceId = buildRaceId(date, venue, raceNo);

    // Normalize keys to numbers: scraper returns "01", "02" strings → 1, 2 numbers
    const normalizeKeys = (obj) => {
      const out = {};
      for (const [k, v] of Object.entries(obj)) out[Number(k)] = v;
      return out;
    };

    results.push({
      race_id: raceId,
      date,
      venue,
      race_no: parseInt(raceNo),
      win: normalizeKeys(odds.win),
      place: normalizeKeys(odds.place),
      scraped_at: new Date()
    });

    const winTop = Object.entries(odds.win).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(',');
    const plaTop = Object.entries(odds.place).slice(0, 2).map(([k, v]) => `${k}=${v}`).join(',');
    console.log(`✅ WIN [${winTop}] PLA [${plaTop}]`);

    // Small delay between races
    await page.waitForTimeout(300);
  }

  await page.close();
  return results;
}

/**
 * Continuous collector loop
 */
async function runCollector(date, venue, races, intervalMs = 15000) {
  console.log(`\n🚀 HKJC Odds Collector starting...`);
  console.log(`📅 ${date} ${venue} | 🏃 Races: ${races.join(', ')}`);
  console.log(`⏱️  Interval: ${intervalMs}ms | 🌐 ${API_BASE}\n`);

  let isFirstRun = true;
  const snapshotSent = new Set();
  let consecutiveFailures = 0;
  let currentInterval = intervalMs;

  const run = async () => {
    let localBrowser = null;
    const startTime = Date.now();
    const timestamp = new Date().toLocaleTimeString();

    try {
      localBrowser = await chromium.launch({
        headless: true,
        channel: 'chrome'
      });
      const results = await scrapeAllRaces(localBrowser, date, venue, races);
      const elapsed = Date.now() - startTime;

      if (results.length === 0) {
        consecutiveFailures++;
        const backoffMs = Math.min(currentInterval * consecutiveFailures, 120000);
        console.log(`[${timestamp}] ❌ No data (${elapsed}ms), failure #${consecutiveFailures}, backing off ${backoffMs}ms`);
        return; // Don't update interval or snapshot state
      }

      // Success — reset failure counter and interval
      consecutiveFailures = 0;
      currentInterval = intervalMs;
      console.log(`[${timestamp}] Scraped ${results.length}/${races.length} races in ${elapsed}ms`);

      // Save to MongoDB
      try {
        const saved = await saveToMongoDB(results);
        console.log(`[${timestamp}] 💾 MongoDB: ${saved} docs`);
      } catch (e) {
        console.error(`[${timestamp}] ⚠️  MongoDB: ${e.message}`);
      }

      // Broadcast to WebSocket clients
      for (const race of results) {
        if (isFirstRun || !snapshotSent.has(race.race_id)) {
          const odds = {};
          const allHorseNos = new Set([
            ...Object.keys(race.win).map(Number),
            ...Object.keys(race.place).map(Number)
          ]);
          for (const h of allHorseNos) {
            odds[h] = {
              win: race.win[h] ?? null,
              place: race.place[h] ?? null
            };
          }
          await broadcastSnapshot(race.race_id, odds);
          snapshotSent.add(race.race_id);
          console.log(`[${timestamp}] 📡 Snapshot → ${race.race_id}`);
        } else {
          for (const [horseNo, winOdds] of Object.entries(race.win)) {
            await broadcastOddsUpdate(race.race_id, Number(horseNo), winOdds, race.place[Number(horseNo)] ?? null);
          }
        }
      }

      isFirstRun = false;
    } catch (e) {
      consecutiveFailures++;
      console.error(`[${timestamp}] ❌ Error: ${e.message}`);
    } finally {
      if (localBrowser) {
        await localBrowser.close().catch(() => {});
      }
    }
  };

  // Run immediately, then on interval
  // Use recursive setTimeout so next interval adapts based on failure count
  let timer = null;
  const scheduleNext = (interval) => {
    timer = setTimeout(async () => {
      await run();
      // If we failed recently, back off exponentially; otherwise use normal interval
      const nextInterval = consecutiveFailures > 0
        ? Math.min(interval * consecutiveFailures, 120000)
        : interval;
      scheduleNext(nextInterval);
    }, interval);
    return timer;
  };

  return scheduleNext(intervalMs);
}

/**
 * One-shot scrape
 */
async function runOnce(date, venue, races) {
  console.log(`\n🎯 One-shot mode: ${date} ${venue} races [${races.join(', ')}]\n`);

  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome'
  });

  const results = await scrapeAllRaces(browser, date, venue, races);
  await browser.close();

  if (results.length > 0) {
    console.log(`\n💾 Saving ${results.length} races to MongoDB...`);
    await saveToMongoDB(results);

    console.log(`\n📡 Broadcasting snapshots...`);
    for (const race of results) {
      const odds = {};
      const allHorseNos = new Set([
        ...Object.keys(race.win).map(Number),
        ...Object.keys(race.place).map(Number)
      ]);
      for (const h of allHorseNos) {
        odds[h] = {
          win: race.win[h] ?? null,
          place: race.place[h] ?? null
        };
      }
      await broadcastSnapshot(race.race_id, odds);
      console.log(`  📡 ${race.race_id}`);
    }
  }

  console.log(`\n✅ Done! Scraped ${results.length} races\n`);
  return results;
}

// CLI
const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h')) {
  console.log(`
HKJC Odds Collector

Usage:
  node odds_collector.js <date> <venue> [options]

Options:
  --continuous    Run continuously (default: one-shot)
  --interval N    Scrape every N ms (default: 5000)
  --races N,...   Specific races (default: 1-10)

Examples:
  node odds_collector.js 2026-03-22 ST
  node odds_collector.js 2026-03-22 ST --continuous
  node odds_collector.js 2026-03-22 ST --continuous --interval 5000 --races 1,2,3
`);
  process.exit(0);
}

const date = args[0] || new Date().toISOString().split('T')[0];
const venue = args[1] || 'ST';

let races = ['1','2','3','4','5','6','7','8','9','10'];
let continuous = false;
let intervalMs = 5000;

for (let i = 2; i < args.length; i++) {
  if (args[i] === '--continuous') { continuous = true; }
  if (args[i] === '--interval' && args[i+1]) { intervalMs = parseInt(args[++i]); }
  if (args[i] === '--races' && args[i+1]) { races = args[++i].split(','); }
}

if (continuous) {
  runCollector(date, venue, races, intervalMs).then((timer) => {
    console.log(`\n🟢 Collector running. Press Ctrl+C to stop.\n`);
    process.on('SIGINT', () => {
      console.log('\n🛑 Stopping collector...');
      clearInterval(timer);
      process.exit(0);
    });
  });
} else {
  runOnce(date, venue, races);
}
