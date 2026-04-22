/**
 * HKJC Live Odds Collector - Smart Scheduling
 * 
 * Logic:
 * - Wake every hour (lightweight check)
 * - Race day: scrape every 5 seconds
 * - Non-race day: scrape only if > 12 hours since last successful scrape
 * - Skip if last scrape < 5 seconds or another scrape in progress
 * - Always keep running (restart on crash)
 * 
 * 2026-04-22 fixes:
 * - Hard timeout wrapper on doScrape (max 12s) so scheduleNext is never blocked
 * - Concurrent race fetching (Promise.all) — all 9 races in parallel
 * - Per-race timeout reduced to 4s (was 8s)
 * - Exponential backoff on consecutive failures
 * - Detailed failure logging (timeout vs empty vs parse error)
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
const MIN_INTERVAL_NON_RACE_DAY = 12 * 60 * 60 * 1000; // 12 hours
const HOURLY_WAKE = 60 * 60 * 1000;           // wake every hour to re-check
const SCRAPE_COOLDOWN = 5 * 1000;              // Skip if < 5s since last

// ─── Retry / Timeout constants ───────────────────────────────────────────────
const RACE_TIMEOUT = 4 * 1000;          // per-race timeout (was 8000ms)
const DO_SCRAPE_HARD_TIMEOUT = 12 * 1000; // hard cap on entire scrapeAllRaces (was unbounded)
const INITIAL_BACKOFF = 5 * 1000;       // first backoff = 5s (same as interval, exponential)
const MAX_BACKOFF = 60 * 1000;          // cap backoff at 60s

// ─── State ─────────────────────────────────────────────────────────────────
let lastScrapeTime = 0;
let isScraping = false;
let finishedRaces = new Set();
let raceScratched = {};
let scheduledTimeout = null;
let logStream = null;

// ─── Backoff state ─────────────────────────────────────────────────────────
let consecutiveFailures = 0;  // how many scrapes returned 0 results in a row
let backoffUntil = 0;         // timestamp — don't scrape until this

// ─── File Logger (with daily rotation) ──────────────────────────────────────
function getLogStream() {
  if (!logStream) {
    const logDir = LOGS_DIR;
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    logStream = createNewLogStream();
  }
  const todayUTC = new Date().toISOString().split('T')[0];
  if (logStream._fileDate !== todayUTC) {
    logStream.end();
    logStream = createNewLogStream();
  }
  return logStream;
}

function createNewLogStream() {
  const logDir = LOGS_DIR;
  const todayUTC = new Date().toISOString().split('T')[0];
  const logFile = path.join(logDir, `odds_${todayUTC}.log`);
  const stream = fs.createWriteStream(logFile, { flags: 'a' });
  stream._fileDate = todayUTC;
  logStream = stream;
  console.log(`[Logger] Writing to ${logFile}`);
  stream.write(`[Logger] Writing to ${logFile}\n`);
  return stream;
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
  const today = now.toLocaleDateString('en-CA', { timeZone: TZ });

  try {
    const db = await getMongo();
    const fixtures = await db.collection('fixtures')
      .find({ date: today, scrape_status: 'completed' })
      .limit(1).toArray();

    if (fixtures.length > 0) {
      log(`[${now.toLocaleTimeString()}] 📅 Race day confirmed: ${fixtures[0].venue}`);
      return { isRaceDay: true, venue: fixtures[0].venue, raceCount: fixtures[0].race_count };
    }

    return { isRaceDay: false };
  } catch (e) {
    console.error(`[${new Date().toLocaleTimeString()}] ⚠️  DB check error: ${e.message}`);
    return { isRaceDay: false };
  }
}

// ─── Get races for today ────────────────────────────────────────────────────
async function getTodayRaces(raceDayResult) {
  const now = new Date();
  const today = now.toLocaleDateString('en-CA', { timeZone: TZ });

  try {
    const db = await getMongo();
    const fixtures = await db.collection('fixtures')
      .find({ date: today, scrape_status: 'completed' })
      .limit(1).toArray();

    if (fixtures.length === 0) return null;

    const fixture = fixtures[0];
    const allRaces = Array.from({ length: fixture.race_count }, (_, i) => i + 1);

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

// ─── Intercept GraphQL ─────────────────────────────────────────────────────
// Returns { data, reason } where reason = 'ok' | 'timeout' | 'no-pools' | 'parse-error'
async function fetchRaceOdds(page, date, venue, raceNo) {
  return new Promise((resolve) => {
    let resolved = false;
    let raceStatuses = null;
    let meetWithPools = null;

    const isResultRace = () => {
      if (!raceStatuses) return false;
      const race = raceStatuses.find(r => String(r.no) === String(raceNo));
      return race && race.status === 'RESULT';
    };

    const resolveIfReady = () => {
      if (resolved) return;
      if (!raceStatuses) return;
      if (!meetWithPools) {
        if (isResultRace()) {
          resolved = true;
          clearTimeout(timeout);
          page.removeListener('response', responseHandler);
          resolve({ data: { raceMeetings: [{ _raceStatuses: raceStatuses }] }, reason: 'ok' });
        }
        return;
      }
      resolved = true;
      clearTimeout(timeout);
      page.removeListener('response', responseHandler);
      meetWithPools._raceStatuses = raceStatuses;
      resolve({ data: { raceMeetings: [meetWithPools] }, reason: 'ok' });
    };

    // Hard timeout — 4 seconds per race (was 8s)
    const timeout = setTimeout(() => {
      if (!resolved) {
        page.removeListener('response', responseHandler);
        if (raceStatuses) {
          resolved = true;
          const meet = meetWithPools || {};
          meet._raceStatuses = raceStatuses;
          resolve({ data: { raceMeetings: [meet] }, reason: 'no-pools' });
        } else {
          // No data at all — mark as timeout
          resolve({ data: null, reason: 'timeout' });
        }
      }
    }, RACE_TIMEOUT);

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
      } catch (e) {
        // Malformed JSON — not critical, wait for next response
      }
    };

    page.on('response', responseHandler);
    page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/${raceNo}`, {
      waitUntil: 'domcontentloaded',
      timeout: 5000  // page navigation timeout — 5s (was 10s)
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

// ─── Scrape all races — CONCURRENT (all races in parallel) ─────────────────
async function scrapeAllRaces(date, venue, races, total) {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();

    // Pre-warm the browser to the HKJC racing page (first race)
    await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
      waitUntil: 'domcontentloaded',
      timeout: 5000
    }).catch(() => {});
    // Give HKJC a moment to serve the initial HTML
    await page.waitForTimeout(1000);

    // Build a fetchRaceOdds promise for each race
    const racePromises = races.map(async (raceNo) => {
      const raceId = buildRaceId(date, venue, raceNo);

      // Skip if already finished (from previous scrape cycle)
      if (finishedRaces.has(raceId)) {
        process.stdout.write(`  Race ${raceNo}/${total}... ⏭ `);
        return { raceNo, status: 'finished', data: null };
      }

      process.stdout.write(`  Race ${raceNo}/${total}... `);

      // fetchRaceOdds resolves in ~1-4s; we wait for ALL races concurrently
      const { data, reason: rawReason } = await fetchRaceOdds(page, date, venue, raceNo);
      let reason = rawReason;

      // Check if race has RESULT
      if (isRaceFinished(data, date, venue, raceNo)) {
        console.log('⏭');
        return { raceNo, status: 'finished', data: null };
      }

      if (!data) {
        console.log(`❌(${reason})`);
        return { raceNo, status: 'no-data', reason, data: null };
      }

      const odds = parseOdds(data);
      if (!odds || (Object.keys(odds.win).length === 0 && Object.keys(odds.place).length === 0)) {
        reason = 'no-pools';
        console.log(`❌(${reason})`);
        return { raceNo, status: 'no-odds', reason, data: null };
      }

      // Collect scratched horses
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
      raceScratched[raceId] = scratchedHorses;

      const result = {
        race_id: raceId,
        date, venue,
        race_no: parseInt(raceNo),
        win: Object.fromEntries(Object.entries(odds.win).map(([k, v]) => [Number(k), v])),
        place: Object.fromEntries(Object.entries(odds.place).map(([k, v]) => [Number(k), v])),
        scratched: scratchedHorses,
        scraped_at: new Date()
      };

      console.log('✅');
      return { raceNo, status: 'ok', data: result };
    });

    // Wait for all races concurrently — total time = slowest race (~4s max)
    const raceResults = await Promise.all(racePromises);

    await browser.close();

    // Collect successful results
    const successful = raceResults
      .filter(r => r.status === 'ok' && r.data)
      .map(r => r.data);

    // Detailed failure summary — count by reason (covers all failure types cleanly)
    const byReason = {};
    raceResults.forEach(r => {
      if (r.status === 'finished') return;
      byReason[r.reason] = (byReason[r.reason] || 0) + 1;
    });
    const failureParts = Object.entries(byReason).map(([k, v]) => `${k}×${v}`);
    const finished = raceResults.filter(r => r.status === 'finished').length;

    if (failureParts.length > 0) {
      log(`[${new Date().toLocaleTimeString()}] ⚠️  Partial: ${failureParts.join(', ')}${finished > 0 ? ` (${finished} finished)` : ''}`);
    }

    return successful;
  } catch (e) {
    await browser.close();
    throw e;
  }
}

// ─── Check if race has results ───────────────────────────────────────────────
function isRaceFinished(data, date, venue, raceNo) {
  const raceId = buildRaceId(date, venue, raceNo);
  const races = data?.data?.raceMeetings?.[0]?._raceStatuses || data?._raceStatuses;
  if (races) {
    const race = races.find(r => String(r.no) === String(raceNo));
    if (race && race.status === 'RESULT') {
      finishedRaces.add(raceId);
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
      console.log('⏭');
      return true;
    }
  }
  if (finishedRaces.has(raceId)) {
    console.log('⏭');
    return true;
  }
  return false;
}

// ─── Save scratched horses to MongoDB ────────────────────────────────────
async function saveScratchedToMongoDB(raceId, scratched) {
  if (!scratched || scratched.length === 0) return;
  try {
    const db = await getMongo();
    const today = raceId.substring(0, 10);
    const venue = raceId.includes('_ST_') ? 'ST' : 'HV';
    const raceNo = parseInt(raceId.split('_R').pop());

    await db.collection('scratched_horses').updateOne(
      { race_id: raceId },
      { $set: { race_id: raceId, horses: scratched, updated_at: new Date() } },
      { upsert: true }
    );

    await db.collection('racecard_entries').updateMany(
      { race_id: raceId, horse_no: { $in: scratched } },
      { $set: { status: 'Scratched' } }
    );

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

    if (allRaceIds) {
      allRaceIds.forEach(raceId => {
        const scratched = raceScratched[raceId];
        if (scratched && scratched.length > 0) {
          if (!body.find(r => r.race_id === raceId)) {
            body.push({ race_id: raceId, odds: {}, scratched });
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

// ─── Main decision: should we scrape now? ─────────────────────────────────
// ─── Main decision: should we scrape now? ─────────────────────────────────
async function maybeScrape() {
  const now = Date.now();

  // Skip if another scrape in progress or cooldown not elapsed
  if (isScraping) return;
  if (lastScrapeTime > 0 && now - lastScrapeTime < SCRAPE_COOLDOWN) return;

  // Backoff: if we're in a backoff window, skip this cycle
  if (backoffUntil > 0 && now < backoffUntil) {
    const remaining = Math.ceil((backoffUntil - now) / 1000);
    log(`[${new Date().toLocaleTimeString()}] ⏱  Backoff ${remaining}s remaining (failures: ${consecutiveFailures})`);
    scheduleNext(1000); // check again in 1s
    return;
  }

  // Check if today is a race day
  const { isRaceDay: raceDayResult } = await isRaceDay().catch(e => {
    log(`[${new Date().toLocaleTimeString()}] ⚠️  isRaceDay failed: ${e.message}`);
    return { isRaceDay: false };
  });

  if (raceDayResult) {
    await doScrape(raceDayResult);
    scheduleNext(SCRAPE_INTERVAL_RACE_DAY);
  } else {
    const elapsed = now - lastScrapeTime;
    const hoursSince = lastScrapeTime === 0 ? 'never' : `${(elapsed / 3600000).toFixed(1)}h`;
    if (elapsed >= MIN_INTERVAL_NON_RACE_DAY) {
      log(`[${new Date().toLocaleTimeString()}] ⏰ Non-race day, ${hoursSince} since last → fetching once`);
      await doScrape(raceDayResult);
    } else {
      log(`[${new Date().toLocaleTimeString()}] ⏰ Non-race day check (${hoursSince} since last, skip < 12h)`);
    }
    scheduleNext(HOURLY_WAKE);
  }
}

// ─── Actual scrape (with hard timeout — never blocks scheduleNext) ────────
// ─── Actual scrape (with hard timeout) ──────────────────────────────────────
async function doScrape(raceDayResult) {
  isScraping = true;
  const startTime = Date.now();
  const now = new Date();
  const today = now.toLocaleDateString('en-CA', { timeZone: TZ });

  try {
    const raceInfo = await getTodayRaces(raceDayResult);

    if (!raceInfo) {
      log(`[${new Date().toLocaleTimeString()}] 📅 No race today`);
      isScraping = false;
      lastScrapeTime = Date.now();
      return;
    }

    const { venue, races, total } = raceInfo;
    const finished = total - races.length;
    log(`[${new Date().toLocaleTimeString()}] 🚀 Scraping ${venue} races [${races.join(', ')}]${finished > 0 ? ` (${finished} finished)` : ''}`);

    await sessionStart(races.map(r => ({ race_id: buildRaceId(today, venue, r) })));

    // Wrap entire scrape in a hard timeout — if it takes > 12s, abort and don't block scheduleNext
    const scrapeResult = await Promise.race([
      scrapeAllRaces(today, venue, races, total),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('SCRAPE_TIMEOUT')), DO_SCRAPE_HARD_TIMEOUT)
      )
    ]).catch(e => {
      if (e.message === 'SCRAPE_TIMEOUT') {
        log(`[${new Date().toLocaleTimeString()}] ⚠️  Scrape hard-timeout after ${DO_SCRAPE_HARD_TIMEOUT / 1000}s — aborting, will retry in next cycle`);
        return []; // treat as partial failure
      }
      throw e;
    });

    if (!scrapeResult) {
      // scrapeResult is undefined only if Promise.race rejected with non-timeout error
      log(`[${new Date().toLocaleTimeString()}] ❌ Scrape error`);
      scrapeResult = [];
    }

    if (scrapeResult.length === 0) {
      log(`[${new Date().toLocaleTimeString()}] ❌ No data (${Date.now() - startTime}ms)`);
      // Exponential backoff: 5s → 10s → 20s → 40s → max 60s
      consecutiveFailures++;
      const backoffMs = Math.min(INITIAL_BACKOFF * Math.pow(2, consecutiveFailures - 1), MAX_BACKOFF);
      backoffUntil = Date.now() + backoffMs;
      log(`[${new Date().toLocaleTimeString()}] 🔁 Backoff ${backoffMs / 1000}s (consecutive failures: ${consecutiveFailures})`);
    } else {
      if (consecutiveFailures > 0) {
        log(`[${new Date().toLocaleTimeString()}] ✅ Recovery after ${consecutiveFailures} failure(s)`);
      }
      consecutiveFailures = 0;
      backoffUntil = 0;
      log(`[${new Date().toLocaleTimeString()}] ✅ Scraped ${scrapeResult.length} races in ${Date.now() - startTime}ms`);
      await saveToMongoDB(scrapeResult);
      await broadcastBatch(scrapeResult, races.map(r => buildRaceId(today, venue, r)));
    }

    lastScrapeTime = Date.now();
    isScraping = false;

  } catch (e) {
    console.error(`[${new Date().toLocaleTimeString()}] ❌ Error: ${e.message}`);
    consecutiveFailures++;
    const backoffMs = Math.min(INITIAL_BACKOFF * Math.pow(2, consecutiveFailures - 1), MAX_BACKOFF);
    backoffUntil = Date.now() + backoffMs;
    isScraping = false;
    lastScrapeTime = Date.now();
  }
}

// ─── Schedule next run ─────────────────────────────────────────────────────
function scheduleNext(interval) {
  if (scheduledTimeout) clearTimeout(scheduledTimeout);
  scheduledTimeout = setTimeout(maybeScrape, interval);
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
║   Race day:     scrape every 5 seconds              ║
║   Non-race day: scrape once if > 12h since last    ║
║   Skip if:     < 5s since last or scrape in prog   ║
║   Backoff:     5→10→20→40→60s on consecutive fails ║
║   Per-race:    4s timeout (concurrent, all 9 races)║
╚══════════════════════════════════════════════════════╝
  `);

  try {
    await maybeScrape();
  } catch (e) {
    log(`[${new Date().toLocaleTimeString()}] ⚠️  maybeScrape crashed: ${e.message}`);
  }
  // Keep-alive heartbeat
  setInterval(() => {}, 25 * 60 * 60 * 1000);
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
