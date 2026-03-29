/**
 * HKJC Live Odds Collector - Smart Scheduling
 * 
 * Logic:
 * - Race day: scrape every 5 seconds
 * - Non-race day: scrape once every 12 hours
 * - Skip if last scrape < 5 seconds or another scrape in progress
 * - Always keep running (restart on crash)
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');
const fs = require('fs');
const path = require('path');

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/';
const DB_NAME = process.env.MONGODB_DATABASE || 'horse_racing';
const API_BASE = process.env.API_BASE || 'http://localhost:3001';
const TZ = 'Asia/Hong_Kong';
const LOGS_DIR = '/app/scrapers/logs';

// ─── Timing constants ───────────────────────────────────────────────────────
const SCRAPE_INTERVAL_RACE_DAY = 5 * 1000;    // 5 seconds
const SCRAPE_INTERVAL_NON_RACE_DAY = 12 * 60 * 60 * 1000; // 12 hours
const SCRAPE_COOLDOWN = 5 * 1000;              // Skip if < 5s since last
const RACE_DAY_CHECK_HOUR = 12;               // Check if race day at noon

// ─── State ─────────────────────────────────────────────────────────────────
let lastScrapeTime = 0;
let isScraping = false;
let currentSchedule = SCRAPE_INTERVAL_NON_RACE_DAY;
let scheduledTimeout = null;
let logStream = null;

// ─── File Logger ─────────────────────────────────────────────────────────
function getLogStream() {
  if (!logStream) {
    const logDir = LOGS_DIR;
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    const logFile = path.join(logDir, `odds_${new Date().toISOString().split('T')[0]}.log`);
    logStream = fs.createWriteStream(logFile, { flags: 'a' });
    log(`[Logger] Writing to ${logFile}`);
  }
  return logStream;
}

function log(...args) {
  const msg = args.join(' ');
  const ts = new Date().toLocaleTimeString('en-GB');
  console.log(msg);
  const stream = getLogStream();
  stream.write(`[${ts}] ${msg}\n`);
}

// ─── MongoDB ────────────────────────────────────────────────────────────────
let mongoClient = null;

async function getMongo() {
  if (!mongoClient) {
    mongoClient = new MongoClient(MONGODB_URI);
    await mongoClient.connect();
  }
  return mongoClient.db(DB_NAME);
}

// ─── Check if today is a race day ─────────────────────────────────────────
async function isRaceDay() {
  const now = new Date();
  const today = now.toISOString().split('T')[0];
  
  try {
    const db = await getMongo();
    const fixtures = await db.collection('fixtures')
      .find({ date: today, scrape_status: 'completed' })
      .limit(1)
      .toArray();
    
    if (fixtures.length > 0) {
      log(`[${now.toLocaleTimeString()}] 📅 Race day confirmed: ${fixtures[0].venue}`);
      return { isRaceDay: true, venue: fixtures[0].venue, raceCount: fixtures[0].race_count };
    }
    
    // Also check tomorrow
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const tomorrowStr = tomorrow.toISOString().split('T')[0];
    const tomorrowFixtures = await db.collection('fixtures')
      .find({ date: tomorrowStr, scrape_status: 'completed' })
      .limit(1)
      .toArray();
    
    if (tomorrowFixtures.length > 0 && now.getHours() >= 12) {
      log(`[${now.toLocaleTimeString()}] 📅 Tomorrow is race day (${tomorrowFixtures[0].venue})`);
      return { isRaceDay: true, venue: tomorrowFixtures[0].venue, raceCount: tomorrowFixtures[0].race_count };
    }
    
    return { isRaceDay: false };
  } catch (e) {
    console.error(`[${new Date().toLocaleTimeString()}] ⚠️  DB check error: ${e.message}`);
    return { isRaceDay: false };
  }
}

// ─── Get races for today ────────────────────────────────────────────────────
async function getTodayRaces() {
  const now = new Date();
  const today = now.toISOString().split('T')[0];
  
  try {
    const db = await getMongo();
    const fixtures = await db.collection('fixtures')
      .find({ date: today, scrape_status: 'completed' })
      .limit(1)
      .toArray();
    
    if (fixtures.length === 0) return null;
    
    const fixture = fixtures[0];
    const races = Array.from({ length: fixture.race_count }, (_, i) => i + 1);
    
    return { venue: fixture.venue, races };
  } catch (e) {
    return null;
  }
}

// ─── Build race ID ─────────────────────────────────────────────────────────
function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

// ─── Intercept GraphQL ─────────────────────────────────────────────────────
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

// ─── Parse odds ────────────────────────────────────────────────────────────
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

// ─── Scrape all races ───────────────────────────────────────────────────────
async function scrapeAllRaces(date, venue, races) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    
    await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    });
    await page.waitForTimeout(2000);

    const results = [];
    for (const raceNo of races) {
      process.stdout.write(`  Race ${raceNo}... `);
      const data = await fetchRaceOdds(page, date, venue, raceNo);
      if (!data) { console.log('❌'); continue; }

      const odds = parseOdds(data);
      if (!odds) { console.log('❌'); continue; }

      const winKeys = Object.keys(odds.win);
      const plaKeys = Object.keys(odds.place);
      if (winKeys.length === 0 && plaKeys.length === 0) { console.log('❌'); continue; }

      const raceId = buildRaceId(date, venue, raceNo);
      results.push({
        race_id: raceId,
        date, venue,
        race_no: parseInt(raceNo),
        win: Object.fromEntries(Object.entries(odds.win).map(([k, v]) => [Number(k), v])),
        place: Object.fromEntries(Object.entries(odds.place).map(([k, v]) => [Number(k), v])),
        scraped_at: new Date()
      });

      log(`✅`);
    }

    await browser.close();
    return results;
  } catch (e) {
    await browser.close();
    throw e;
  }
}

// ─── Save to MongoDB ───────────────────────────────────────────────────────
async function saveToMongoDB(docs) {
  if (docs.length === 0) return 0;
  const db = await getMongo();
  const result = await db.collection('live_odds').insertMany(
    docs.map(d => ({ ...d, scraped_at: new Date() }))
  );
  return result.insertedCount;
}

// ─── Broadcast batch ───────────────────────────────────────────────────────
async function broadcastBatch(races) {
  if (races.length === 0) return;
  try {
    const body = races.map(race => ({
      race_id: race.race_id,
      odds: Object.fromEntries(
        Object.keys(race.win).map(hk => [
          Number(hk),
          { win: race.win[hk], place: race.place?.[hk] }
        ])
      )
    }));
    await fetch(`${API_BASE}/api/odds/batch-snapshot`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ races: body })
    });
  } catch (e) {
    console.error(`[${new Date().toLocaleTimeString()}] ⚠️ Broadcast failed: ${e.message}`);
  }
}

// ─── Session tracking ───────────────────────────────────────────────────────
async function sessionStart(races) {
  for (const race of races) {
    try {
      await fetch(`${API_BASE}/api/odds/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ race_id: race.race_id })
      });
    } catch (e) {}
  }
}

async function sessionEnd(races) {
  for (const race of races) {
    try {
      await fetch(`${API_BASE}/api/odds/session/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ race_id: race.race_id })
      });
    } catch (e) {}
  }
}

// ─── Main scrape cycle ─────────────────────────────────────────────────────
async function scrapeCycle() {
  const now = Date.now();
  
  // Skip if another scrape in progress
  if (isScraping) {
    log(`[${new Date().toLocaleTimeString()}] ⏳ Scrape in progress, skipping...`);
    return;
  }
  
  // Skip if cooldown not elapsed
  if (now - lastScrapeTime < SCRAPE_COOLDOWN) {
    return;
  }
  
  isScraping = true;
  const startTime = Date.now();
  const today = new Date().toISOString().split('T')[0];
  
  try {
    const raceInfo = await getTodayRaces();
    
    if (!raceInfo) {
      log(`[${new Date().toLocaleTimeString()}] 📅 No race today, sleeping 12h`);
      isScraping = false;
      lastScrapeTime = now;
      scheduleNext(SCRAPE_INTERVAL_NON_RACE_DAY);
      return;
    }
    
    const { venue, races } = raceInfo;
    log(`[${new Date().toLocaleTimeString()}] 🚀 Scraping ${venue} races [${races.join(', ')}]`);
    
    // Session start
    await sessionStart(races.map(r => ({ race_id: buildRaceId(today, venue, r) })));
    
    const results = await scrapeAllRaces(today, venue, races);
    
    if (results.length === 0) {
      log(`[${new Date().toLocaleTimeString()}] ❌ No data`);
    } else {
      log(`[${new Date().toLocaleTimeString()}] ✅ Scraped ${results.length} races in ${Date.now() - startTime}ms`);
      
      await saveToMongoDB(results);
      await broadcastBatch(results);
    }
    
    lastScrapeTime = Date.now();
    isScraping = false;
    
    // Schedule next based on whether it's still race day
    scheduleNext(SCRAPE_INTERVAL_RACE_DAY);
    
  } catch (e) {
    console.error(`[${new Date().toLocaleTimeString()}] ❌ Error: ${e.message}`);
    isScraping = false;
    lastScrapeTime = Date.now();
    scheduleNext(SCRAPE_INTERVAL_RACE_DAY);
  }
}

// ─── Schedule next run ─────────────────────────────────────────────────────
function scheduleNext(interval) {
  if (scheduledTimeout) clearTimeout(scheduledTimeout);
  scheduledTimeout = setTimeout(scrapeCycle, interval);
}

// ─── Graceful shutdown ─────────────────────────────────────────────────────
async function shutdown() {
  console.log('\n🛑 Shutting down...');
  if (scheduledTimeout) clearTimeout(scheduledTimeout);
  try {
    await mongoClient?.close();
  } catch (e) {}
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// ─── Start ─────────────────────────────────────────────────────────────────
async function main() {
  log(`
╔══════════════════════════════════════════════════════╗
║   🏇 HKJC Odds Collector - Smart Schedule           ║
╠══════════════════════════════════════════════════════╣
║   Race day:     every 5 seconds                     ║
║   Non-race day: every 12 hours                      ║
║   Skip if:     < 5s since last or scrape in prog   ║
╚══════════════════════════════════════════════════════╝
  `);
  
  // Check race day status periodically
  const checkRaceDay = async () => {
    const { isRaceDay: raceDayResult, venue } = await isRaceDay();
    const newInterval = raceDayResult ? SCRAPE_INTERVAL_RACE_DAY : SCRAPE_INTERVAL_NON_RACE_DAY;
    
    if (newInterval !== currentSchedule) {
      log(`[${new Date().toLocaleTimeString()}] 📅 Schedule changed: ${currentSchedule === SCRAPE_INTERVAL_RACE_DAY ? 'Race day' : 'Non-race day'} → ${raceDayResult ? 'Race day' : 'Non-race day'}`);
      currentSchedule = newInterval;
    }
    
    // Reschedule with new interval
    scheduleNext(1000); // Quick re-check
  };
  
  // Check race day status every hour
  setInterval(checkRaceDay, 60 * 60 * 1000);
  
  // Initial scrape
  await scrapeCycle();
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
