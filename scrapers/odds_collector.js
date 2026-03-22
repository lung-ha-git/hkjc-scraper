/**
 * HKJC Live Odds Collector
 * 
 * Scrapes odds every 5 seconds and broadcasts via WebSocket.
 * Also writes to MongoDB for persistence.
 * 
 * Usage:
 *   node odds_collector.js [date] [venue]
 *   node odds_collector.js 2026-03-22 ST
 * 
 * Run on a schedule or continuously during race day.
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
 * Intercept GraphQL response to get odds
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
 * Parse odds from GraphQL response
 * Returns { win: { horse_no, odds }, place: { horse_no, odds } }
 */
function parseOdds(data, raceNo) {
  if (!data?.data?.raceMeetings?.[0]?.pmPools) return null;

  const meeting = data.data.raceMeetings[0];
  const result = { race_id: null, win: {}, place: {} };

  meeting.pmPools?.forEach(pool => {
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

/**
 * Broadcast single odds update to WebSocket server
 */
async function broadcastOddsUpdate(raceId, horseNo, win, place) {
  try {
    await fetch(`${API_BASE}/api/odds/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId, horse_no: horseNo, win, place })
    });
  } catch (e) {
    console.error(`  ⚠️  Broadcast failed for ${raceId} #${horseNo}: ${e.message}`);
  }
}

/**
 * Broadcast full snapshot to WebSocket server
 */
async function broadcastSnapshot(raceId, odds) {
  try {
    await fetch(`${API_BASE}/api/odds/snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ race_id: raceId, odds })
    });
  } catch (e) {
    console.error(`  ⚠️  Snapshot broadcast failed for ${raceId}: ${e.message}`);
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
 * Scrape all races and return array of parsed results
 */
async function scrapeAllRaces(browser, date, venue, races) {
  const page = await browser.newPage();

  // Intercept all responses
  const responseMap = {}; // raceNo -> parsed data
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;

    try {
      const body = await response.text();
      if (!body.includes('"pmPools"') || !body.includes('"oddsNodes"')) return;

      const json = JSON.parse(body);
      const pools = json?.data?.raceMeetings?.[0]?.pmPools;
      if (!pools) return;

      // Extract race number from the URL
      const match = url.match(/\/(ST|HV)\/(\d+)$/);
      if (!match) return;
      const raceNo = match[2];

      responseMap[raceNo] = json;
    } catch (e) {}
  });

  // Establish session first
  console.log('🔐 Establishing session...');
  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });
  await page.waitForTimeout(3000);
  console.log('✅ Session ready\n');

  // Fetch each race
  for (const raceNo of races) {
    await fetchRaceOdds(page, date, venue, raceNo);
    await page.waitForTimeout(500);
  }

  await page.close();

  // Parse all intercepted responses
  const results = [];
  for (const raceNo of races) {
    const data = responseMap[raceNo];
    if (!data) continue;

    const parsed = parseOdds(data, raceNo);
    if (!parsed) continue;

    const raceId = buildRaceId(date, venue, raceNo);
    parsed.race_id = raceId;
    parsed.date = date;
    parsed.venue = venue;
    parsed.race_no = parseInt(raceNo);
    parsed.scraped_at = new Date();

    results.push(parsed);
  }

  return results;
}

/**
 * Get list of active races from MongoDB fixtures
 */
async function getActiveRaces(date, venue) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const racecards = await client.db(DB_NAME).collection('racecards')
      .find({ race_date: date })
      .project({ race_no: 1 })
      .toArray();
    return racecards.map(r => String(r.race_no));
  } finally {
    await client.close();
  }
}

/**
 * Continuous collector loop
 */
async function runCollector(date, venue, races, intervalMs = 5000) {
  console.log(`\n🚀 HKJC Odds Collector starting...`);
  console.log(`📅 ${date} ${venue} | 🏃 Races: ${races.join(', ')}`);
  console.log(`⏱️  Interval: ${intervalMs}ms | 🌐 ${API_BASE}\n`);

  const browser = await chromium.launch({
    headless: true,
    channel: 'chrome'
  });

  let isFirstRun = true;
  let snapshotSent = {};

  const run = async () => {
    const startTime = Date.now();
    process.stdout.write(`[${new Date().toLocaleTimeString()}] Scraping... `);

    try {
      const results = await scrapeAllRaces(browser, date, venue, races);
      const elapsed = Date.now() - startTime;

      if (results.length === 0) {
        console.log(`❌ (${elapsed}ms) - no data`);
        return;
      }

      console.log(`✅ ${results.length}/${races.length} races (${elapsed}ms)`);

      // Save to MongoDB
      try {
        await saveToMongoDB(results);
      } catch (e) {
        console.error(`  ⚠️  MongoDB save failed: ${e.message}`);
      }

      // Broadcast to WebSocket clients
      for (const race of results) {
        const raceId = race.race_id;

        if (isFirstRun || !snapshotSent[raceId]) {
          // Send full snapshot on first run
          const odds = {};
          const allHorseNos = new Set([
            ...Object.keys(race.win),
            ...Object.keys(race.place)
          ]);
          for (const h of allHorseNos) {
            odds[h] = {
              win: race.win[h] ?? null,
              place: race.place[h] ?? null
            };
          }
          await broadcastSnapshot(raceId, odds);
          snapshotSent[raceId] = true;
          console.log(`  📡 Snapshot → ${raceId}`);
        } else {
          // Send incremental updates
          for (const [horseNo, win] of Object.entries(race.win)) {
            await broadcastOddsUpdate(raceId, horseNo, win, race.place[horseNo] ?? null);
          }
        }
      }

      isFirstRun = false;
    } catch (e) {
      console.error(`❌ Error: ${e.message}`);
    }
  };

  // Run immediately, then on interval
  await run();
  return setInterval(run, intervalMs);
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
        ...Object.keys(race.win),
        ...Object.keys(race.place)
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
  --continuous    Run continuously (default: false, one-shot)
  --interval N    Scrape every N ms (default: 5000)
  --races N,...   Specific races (default: 1-10)
  --help, -h      Show this help

Examples:
  node odds_collector.js 2026-03-22 ST
  node odds_collector.js 2026-03-22 ST --continuous --interval 5000
  node odds_collector.js 2026-03-22 ST --races 1,2,3,4,5
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
      console.log('\n\n🛑 Stopping collector...');
      clearInterval(timer);
      process.exit(0);
    });
  });
} else {
  runOnce(date, venue, races);
}
