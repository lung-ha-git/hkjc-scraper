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
let finishedRaces = new Set();  // races that have results - never scrape again
let raceScratched = {};                 // race_id -> [scratched horse nos]
let hasSynced = false;                  // sync runner status only once
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
    const allRaces = Array.from({ length: fixture.race_count }, (_, i) => i + 1);
    
    // Filter out already finished races
    const unfinished = allRaces.filter(no => {
      const raceId = buildRaceId(today, fixture.venue, no);
      return !finishedRaces.has(raceId);
    });
    
    if (unfinished.length === 0) {
      log(`[${new Date().toLocaleTimeString()}] 🎉 全部 ${allRaces.length} 場已結算，停止 Collector`);
      return null;
    }
    
    return { venue: fixture.venue, races: unfinished, total: allRaces.length };
  } catch (e) {
    return null;
  }
}

// ─── Build race ID ─────────────────────────────────────────────────────────
function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

// ─── Check if race has results (finished) ──────────────────────────────────────
// Check race status from races[] array (may be in data._raceStatuses or raceScratched cache)
function isRaceFinished(data, date, venue, raceNo) {
  const raceId = buildRaceId(date, venue, raceNo);
  // Check races[] from the data we just fetched
  const races = data?.data?.raceMeetings?.[0]?._raceStatuses || data?._raceStatuses;
  if (races) {
    const race = races.find(r => String(r.no) === String(raceNo));
    if (race && race.status === 'RESULT') {
      finishedRaces.add(raceId);
      // Collect scratched horses from races[] data
      const scratched = [];
      if (race.runners) {
        race.runners.forEach(runner => {
          if (runner.status === 'Scratched') {
            scratched.push(Number(runner.no));
          }
        });
      }
      if (scratched.length > 0) {
        raceScratched[raceId] = scratched;
        saveScratchedToMongoDB(raceId, scratched);
      }
      console.log(`⏭ 已結算`);
      return true;
    }
  }
  // RESULT race already in our finished set (from previous cycle)
  if (finishedRaces.has(raceId)) {
    console.log(`⏭ 已結算`);
    return true;
  }
  return false;
}

// ─── Intercept GraphQL ─────────────────────────────────────────────────────
async function fetchRaceOdds(page, date, venue, raceNo) {
  return new Promise((resolve) => {
    let resolved = false;
    let raceStatuses = null;
    let meetWithPools = null;
    
    // Check if this race is RESULT (no pmPools will come)
    const isResultRace = () => {
      if (!raceStatuses) return false;
      const race = raceStatuses.find(r => String(r.no) === String(raceNo));
      return race && race.status === 'RESULT';
    };
    
    const resolveIfReady = () => {
      if (resolved) return;
      // Need pmPools AND races[] for normal races, OR just races[] for RESULT races
      if (!raceStatuses) return;
      if (!meetWithPools) {
        // No pmPools - could be RESULT race or still loading
        if (isResultRace()) {
          // RESULT race - resolve immediately with races[] data
          resolved = true;
          clearTimeout(timeout);
          page.removeListener('response', responseHandler);
          resolve({ data: { raceMeetings: [{ _raceStatuses: raceStatuses }] } });
        }
        return;
      }
      resolved = true;
      clearTimeout(timeout);
      page.removeListener('response', responseHandler);
      meetWithPools._raceStatuses = raceStatuses;
      resolve({ data: { raceMeetings: [meetWithPools] } });
    };
    
    const timeout = setTimeout(() => {
      if (!resolved) {
        page.removeListener('response', responseHandler);
        // No pmPools - resolve with races[] if available (RESULT races have no odds)
        if (raceStatuses) {
          resolved = true;
          const meet = meetWithPools || {};
          meet._raceStatuses = raceStatuses;
          resolve({ data: { raceMeetings: [meet] } });
        } else {
          resolve(null);
        }
      }
    }, 8000);

    const responseHandler = async (response) => {
      const url = response.url();
      if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
      if (resolved) return;
      try {
        const body = await response.text();
        const json = JSON.parse(body);
        const meet = json?.data?.raceMeetings?.[0];
        if (!meet) return;
        
        if (meet.races) {
          raceStatuses = meet.races;
          resolveIfReady();
        }
        
        if (meet.pmPools && meet.pmPools.length > 0) {
          meetWithPools = meet;
          resolveIfReady();
        }
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
async function scrapeAllRaces(date, venue, races, total) {
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
      const raceId = buildRaceId(date, venue, raceNo);
      
      // Skip if already finished (from previous scrape cycle)
      if (finishedRaces.has(raceId)) {
        console.log(`  Race ${raceNo}/${total}... ⏭ 已結算`);
        continue;
      }
      
      process.stdout.write(`  Race ${raceNo}/${total}... `);
      const data = await fetchRaceOdds(page, date, venue, raceNo);
      
      if (isRaceFinished(data, date, venue, raceNo)) { console.log(''); continue; }
      if (!data) { console.log('❌'); continue; }

      const odds = parseOdds(data);
      if (!odds) { console.log('❌'); continue; }

      const winKeys = Object.keys(odds.win);
      const plaKeys = Object.keys(odds.place);
      if (winKeys.length === 0 && plaKeys.length === 0) { console.log('❌'); continue; }
      
      // Collect scratched horses from races data
      const scratchedHorses = [];
      const racesData = data?.data?.raceMeetings?.[0]?._raceStatuses;
      const raceInfo = racesData?.find(r => String(r.no) === String(raceNo));
      if (raceInfo?.runners) {
        raceInfo.runners.forEach(runner => {
          if (runner.status === 'Scratched') {
            scratchedHorses.push(Number(runner.no));
          }
        });
      }
      // Store globally so we can broadcast even for RESULT races
      raceScratched[raceId] = scratchedHorses;
      
      // Persist to MongoDB
      if (scratchedHorses.length > 0) {
        saveScratchedToMongoDB(raceId, scratchedHorses);
      }

      const result = {
        race_id: raceId,
        date, venue,
        race_no: parseInt(raceNo),
        win: Object.fromEntries(Object.entries(odds.win).map(([k, v]) => [Number(k), v])),
        place: Object.fromEntries(Object.entries(odds.place).map(([k, v]) => [Number(k), v])),
        scratched: scratchedHorses,
        scraped_at: new Date()
      };
      results.push(result);

      console.log('✅');
    }

    await browser.close();
    return results;
  } catch (e) {
    await browser.close();
    throw e;
  }
}

// ─── Save scratched horses to MongoDB ────────────────────────────────────
async function saveScratchedToMongoDB(raceId, scratched) {
  if (!scratched || scratched.length === 0) return;
  try {
    const db = await getMongo();
    const today = raceId.substring(0, 10);  // YYYY-MM-DD
    const venue = raceId.includes('_ST_') ? 'ST' : 'HV';
    const raceNo = parseInt(raceId.split('_R').pop());
    
    // Save to scratched_horses collection
    await db.collection('scratched_horses').updateOne(
      { race_id: raceId },
      { $set: { race_id: raceId, horses: scratched, updated_at: new Date() } },
      { upsert: true }
    );
    
    // Update racecard_entries collection with correct status
    await db.collection('racecard_entries').updateMany(
      { race_id: raceId, horse_no: { $in: scratched } },
      { $set: { status: 'Scratched' } }
    );
    
    // Also update embedded horses in racecards collection
    for (const hn of scratched) {
      await db.collection('racecards').updateOne(
        { race_date: today, race_no: raceNo, 'horses.horse_no': hn },
        { $set: { 'horses.$.status': 'Scratched' } }
      );
    }
  } catch (e) {
    console.error('saveScratchedToMongoDB error:', e.message);
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
async function broadcastBatch(races, allRaceIds) {
  if (races.length === 0) return;
  try {
    // Build odds payload for scraped races
    const body = races.map(race => ({
      race_id: race.race_id,
      odds: Object.fromEntries(
        Object.keys(race.win).map(hk => [
          Number(hk),
          { win: race.win[hk], place: race.place?.[hk] }
        ])
      ),
      scratched: race.scratched || raceScratched[race.race_id] || []
    }));
    
    // Also broadcast scratched for RESULT races (not scraped this cycle)
    if (allRaceIds) {
      allRaceIds.forEach(raceId => {
        const scratched = raceScratched[raceId];
        if (scratched && scratched.length > 0) {
          // Check if already in body
          if (!body.find(r => r.race_id === raceId)) {
            body.push({
              race_id: raceId,
              odds: {},
              scratched: scratched
            });
          }
        }
      });
    }
    
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
  
  // Sync runner status from HKJC GraphQL to MongoDB (first cycle only)
  if (!hasSynced) {
    hasSynced = true;
    syncRunnerStatus().catch(() => {});
  }
  
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
    
    const { venue, races, total } = raceInfo;
    const finished = total - races.length;
    log(`[${new Date().toLocaleTimeString()}] 🚀 Scraping ${venue} races [${races.join(', ')}]${finished > 0 ? ` (${finished} finished)` : ''}`);
    
    // Session start
    await sessionStart(races.map(r => ({ race_id: buildRaceId(today, venue, r) })));
    
    const results = await scrapeAllRaces(today, venue, races, total);
    
    if (results.length === 0) {
      log(`[${new Date().toLocaleTimeString()}] ❌ No data`);
    } else {
      log(`[${new Date().toLocaleTimeString()}] ✅ Scraped ${results.length} races in ${Date.now() - startTime}ms`);
      
      await saveToMongoDB(results);
      await broadcastBatch(results, races.map(r => buildRaceId(today, venue, r)));
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
