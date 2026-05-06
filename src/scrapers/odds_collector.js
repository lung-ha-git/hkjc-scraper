/**
 * HKJC Live Odds Collector
 *
 * Logic:
 * - Wake every hour (lightweight check)
 * - Race day: scrape every 20 seconds (9 races take ~12s)
 * - Non-race day: scrape only if > 12 hours since last successful scrape
 * - Skip if last scrape < 5 seconds or another scrape in progress
 * - Always keep running (restart on crash)
 *
 * Architecture:
 * - Uses Playwright to load the SPA and intercept GraphQL responses
 * - Page.on('response') intercepts odds as they arrive
 * - Falls back to GraphQL HTTP polling if MQTT push isn't available
 */

const { MongoClient } = require('mongodb');
const { chromium } = require('playwright');
const mqtt = require('mqtt');
const fs = require('fs');
const path = require('path');

const MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/';
const DB_NAME = process.env.MONGODB_DATABASE || 'horse_racing';
const API_BASE = process.env.API_BASE || 'http://localhost:3001';
const TZ = 'Asia/Hong_Kong';
const LOGS_DIR = '/app/scrapers/logs';

// ─── Timing constants ───────────────────────────────────────────────────────
const SCRAPE_INTERVAL_RACE_DAY = 20 * 1000;    // 20 seconds — 9 races take ~12s, gives 8s buffer
const MIN_INTERVAL_NON_RACE_DAY = 12 * 60 * 60 * 1000; // 12 hours
const HOURLY_WAKE = 60 * 60 * 1000;           // wake every hour to re-check
const SCRAPE_COOLDOWN = 5 * 1000;              // Skip if < 5s since last

// ─── Retry / Timeout constants ───────────────────────────────────────────────
const RACE_TIMEOUT = 12 * 1000;         // per-race timeout — HKJC odds load ~10s after page load
const DO_SCRAPE_HARD_TIMEOUT = 120 * 1000; // hard cap on entire scrapeAllRaces (9 races × 12s = 108s)
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
  const today = process.env.RACE_DATE || now.toLocaleDateString('en-CA', { timeZone: TZ });

  try {
    const db = await getMongo();
    const fixtures = await db.collection('fixtures')
      .find({ date: today, scrape_status: 'completed' })
      .limit(1).toArray();

    if (fixtures.length > 0) {
      log(`[${now.toLocaleTimeString()}] 📅 Race day confirmed: ${fixtures[0].venue} (${fixtures[0].race_date})`);
      return { isRaceDay: true, venue: fixtures[0].venue, raceCount: fixtures[0].race_count, raceDate: fixtures[0].race_date };
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
  const today = process.env.RACE_DATE || now.toLocaleDateString('en-CA', { timeZone: TZ });

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

// ─── Intercept MQTT (live odds push) ────────────────────────────────────────
// HKJC new SPA uses MQTT over WSS for live odds. This replaces GraphQL polling.
// Returns { data, reason } where reason = 'ok' | 'timeout' | 'no-pools' | 'parse-error'
async function fetchRaceOdds_MQTT(date, venue, raceNo) {
  return new Promise((resolve) => {
    let resolved = false;
    let oddsData = null;
    let mqttClient = null;

    const cleanup = () => {
      resolved = true;
      if (mqttClient) {
        try { mqttClient.end(true); } catch (e) {}
      }
    };

    const timeout = setTimeout(() => {
      if (!resolved) {
        cleanup();
        resolve({ data: oddsData, reason: oddsData ? 'no-pools' : 'timeout' });
      }
    }, RACE_TIMEOUT);

    // Connect to HKJC MQTT broker over WebSocket
    // Credentials extracted from bet.hkjc.com SPA JS:
    //   PUSH_URL_NOLOGIN = "wss://ueb.hkjc.com:52443/" (use this for no-login / RC_ODDS_PUSH_NO_LOGIN=true)
    //   username: "jcbw2"
    //   password: window.globalConfig.PUSH_NO_LOGIN_SECRET = "2Wt5tGOzRm]yp~N"
    //   protocolVersion: 5 (MQTT 5.0)
    const MQTT_URL = 'wss://ueb.hkjc.com:52443/';
    const MQTT_OPTS = {
      username: 'jcbw2',
      password: '2Wt5tGOzRm]yp~N',
      rejectUnauthorized: false,
      clientId: `hkjc_odds_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      clean: true,
      connectTimeout: 8000,
      keepalive: 60,
    };

    try {
      mqttClient = mqtt.connect(MQTT_URL, MQTT_OPTS);

      mqttClient.on('connect', () => {
        console.error(`[MQTT] Connected to ${MQTT_URL}`);
        // Subscribe to all racing topics — narrow down per race after getting data
        mqttClient.subscribe('racing/#', { qos: 0 }, (err) => {
          if (err) {
            console.error(`[MQTT] Subscribe error: ${err.message}`);
            cleanup();
            resolve({ data: null, reason: 'timeout' });
          } else {
            console.error('[MQTT] Subscribed to racing/#');
          }
        });
      });

      mqttClient.on('message', (topic, message) => {
        if (resolved) return;
        try {
          const payload = JSON.parse(message.toString());
          console.error(`[MQTT] MSG ${topic}:`, JSON.stringify(payload).substring(0, 200));

          // Parse topic: racing/YYYY-MM-DD/ST/R1 or similar
          // Extract odds data from the payload
          const topicParts = topic.split('/');
          const topicRaceNo = topicParts[topicParts.length - 1]?.replace('R', '') || '';

          if (String(topicRaceNo) !== String(raceNo)) return;

          // Extract odds from MQTT payload
          // The payload structure varies — look for winOdds, qnOdds, pmPools, etc.
          const rawOdds = extractOddsFromMQTT(payload, raceNo);
          if (rawOdds && (Object.keys(rawOdds.win || {}).length > 0 || Object.keys(rawOdds.place || {}).length > 0)) {
            oddsData = rawOdds;
            cleanup();
            resolve({ data: rawOdds, reason: 'ok' });
          }
        } catch (e) {
          // Not JSON or parse error — ignore
        }
      });

      mqttClient.on('error', (err) => {
        console.error(`[MQTT] Error: ${err.message}`);
        if (!resolved) {
          cleanup();
          resolve({ data: null, reason: 'timeout' });
        }
      });

      mqttClient.on('close', () => {
        if (!resolved) {
          cleanup();
          resolve({ data: oddsData, reason: oddsData ? 'no-pools' : 'timeout' });
        }
      });

    } catch (e) {
      clearTimeout(timeout);
      resolve({ data: null, reason: 'timeout' });
    }
  });
}

// Extract structured odds from MQTT payload (structure varies — handle flexibly)
function extractOddsFromMQTT(payload, raceNo) {
  // Handle different HKJC MQTT message formats
  // Format 1: { oddsType: 'WIN', oddsValue: '1.2', combString: '1' }
  // Format 2: { pools: { WIN: { '1': 1.2, '2': 2.1 }, PLA: { '1': 1.1 } } }
  // Format 3: { winOdds: { '1': 1.2 }, placeOdds: { '1': 1.1 } }
  // Format 4: { pmPools: [{ oddsType: 'WIN', oddsNodes: [{ combString: '1', oddsValue: '1.2' }] }] }

  const result = { win: {}, place: {} };

  // Try Format 4: pmPools array
  if (payload.pmPools && Array.isArray(payload.pmPools)) {
    for (const pool of payload.pmPools) {
      const target = pool.oddsType === 'WIN' ? result.win
                   : pool.oddsType === 'PLA' ? result.place
                   : null;
      if (!target) continue;
      if (pool.oddsNodes && Array.isArray(pool.oddsNodes)) {
        for (const node of pool.oddsNodes) {
          if (node.combString && node.oddsValue != null) {
            target[String(node.combString)] = parseFloat(node.oddsValue);
          }
        }
      }
    }
    if (Object.keys(result.win).length > 0 || Object.keys(result.place).length > 0) {
      return result;
    }
  }

  // Try Format 2: pools.WIN / pools.PLA
  if (payload.pools) {
    for (const [poolType, oddsMap] of Object.entries(payload.pools)) {
      if (!oddsMap || typeof oddsMap !== 'object') continue;
      const target = poolType === 'WIN' ? result.win
                   : poolType === 'PLA' || poolType === 'PLACE' ? result.place
                   : null;
      if (!target) continue;
      for (const [horseNo, val] of Object.entries(oddsMap)) {
        if (val != null) target[String(horseNo)] = parseFloat(val);
      }
    }
    if (Object.keys(result.win).length > 0 || Object.keys(result.place).length > 0) {
      return result;
    }
  }

  // Try Format 3: winOdds / placeOdds
  if (payload.winOdds || payload.placeOdds) {
    for (const [horseNo, val] of Object.entries(payload.winOdds || {})) {
      if (val != null) result.win[String(horseNo)] = parseFloat(val);
    }
    for (const [horseNo, val] of Object.entries(payload.placeOdds || {})) {
      if (val != null) result.place[String(horseNo)] = parseFloat(val);
    }
    if (Object.keys(result.win).length > 0 || Object.keys(result.place).length > 0) {
      return result;
    }
  }

  // Try direct odds array format: [{ horseNo, odds, type }]
  if (Array.isArray(payload)) {
    for (const item of payload) {
      if (!item || item.odds == null) continue;
      const target = item.type === 'WIN' ? result.win
                   : item.type === 'PLA' || item.type === 'PLACE' ? result.place
                   : null;
      if (!target) continue;
      target[String(item.horseNo || item.no || item.combString)] = parseFloat(item.odds);
    }
    if (Object.keys(result.win).length > 0 || Object.keys(result.place).length > 0) {
      return result;
    }
  }

  return null;
}

// ─── Intercept GraphQL (fallback / pre-race metadata) ──────────────────────
// Kept as fallback for pre-race data when MQTT isn't available
async function fetchRaceOdds_GraphQL(page, date, venue, raceNo) {
  return new Promise((resolve) => {
    let resolved = false;
    let raceStatuses = null;
    let meetWithPools = null;

    const resolveIfReady = () => {
      if (resolved) return;
      if (!raceStatuses) return;
      if (!meetWithPools) return;
      resolved = true;
      clearTimeout(timeout);
      page.removeListener('response', responseHandler);
      meetWithPools._raceStatuses = raceStatuses;
      resolve({ data: { raceMeetings: [meetWithPools] }, reason: 'ok' });
    };

    const timeout = setTimeout(() => {
      if (!resolved) {
        page.removeListener('response', responseHandler);
        if (raceStatuses) {
          resolved = true;
          const meet = meetWithPools || {};
          meet._raceStatuses = raceStatuses;
          resolve({ data: { raceMeetings: [meet] }, reason: 'no-pools' });
        } else {
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
        }

        if (meet.pmPools && meet.pmPools.length > 0) {
          meetWithPools = meet;
          resolveIfReady();
        }
      } catch (e) {
        // Malformed JSON — ignore
      }
    };

    page.on('response', responseHandler);
    page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/${raceNo}`, {
      waitUntil: 'domcontentloaded',
      timeout: 15000
    }).catch(() => {});
  });
}

// Extract structured odds from MQTT payload
// MQTT delivers live odds push; GraphQL delivers race metadata + odds (when available).
// We race them and merge: use MQTT odds if available, GraphQL status regardless.
async function fetchRaceOdds(browser, date, venue, raceNo) {
  let raceStatuses = null;
  let oddsData = null;
  let resolved = false;
  let page = null;
  let mqttClient = null;
  let graphqlResolved = false;

  const cleanup = () => {
    resolved = true;
    if (mqttClient) { try { mqttClient.end(true); } catch (e) {} }
    if (page) { try { page.close(); page = null; } catch (e) { page = null; } }
  };

  const cleanupFns = [];

  // Create page BEFORE registering handlers — required for "handler before goto" pattern
  try {
    page = await browser.newPage();
  } catch (e) {
    // Browser context disposed — return timeout immediately
    return { data: null, raceStatuses: null, reason: 'timeout' };
  }

  // GraphQL intercept — keep listening until we get a response with pmPools > 0,
  // OR until RACE_TIMEOUT fires. HKJC sends the first response (pools=0) quickly,
  // but the odds data arrives ~150ms later in a subsequent response.
  const gotoUrl = `https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/${raceNo}`;

  const graphqlPromise = new Promise((resolve) => {
    const graphqlTimeout = setTimeout(() => {
      // Timeout — resolve with whatever we have (may be null if no pools ever arrived)
      resolve({ data: oddsData, raceStatuses, reason: oddsData ? 'ok' : 'no-pools' });
    }, RACE_TIMEOUT);

    cleanupFns.push(() => { clearTimeout(graphqlTimeout); });

    // Start navigation (non-blocking) — domcontentloaded fires ~830ms
    global._scrapeStart = Date.now();
    void page.goto(gotoUrl, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(e => {
      if (!resolved) console.error(`[SCRAPE] goto error: ${e.message}`);
    });

    // Intercept all GraphQL responses until we get one with pools, or timeout
    const onResponse = async (response) => {
      const ms = Date.now() - (global._scrapeStart || 0);
      const url = response.url();
      if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
      try {
        const body = await response.text();
        const json = JSON.parse(body);
        const meet = json?.data?.raceMeetings?.[0];
        if (!meet) return;
        if (meet.races) raceStatuses = meet.races;
        if (meet.pmPools && meet.pmPools.length > 0) {
          clearTimeout(graphqlTimeout);
          oddsData = parseOdds({ data: { raceMeetings: [meet] } });
          page.removeListener('response', onResponse);
          resolve({ data: oddsData, raceStatuses, reason: 'ok' });
        } else {
        }
      } catch (e) {
      }
    };
    page.on('response', onResponse);
  });

  // MQTT subscription in background
  const mqttPromise = new Promise((resolve) => {
    const MQTT_URL = 'wss://ueb.hkjc.com:52443/';
    const MQTT_OPTS = {
      username: 'jcbw2',
      password: '2Wt5tGOzRm]yp~N',
      rejectUnauthorized: false,
      clientId: `hkjc_odds_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      clean: true,
      connectTimeout: 4000,
    };

    let mqttTimeout;
    let mqttResolved = false;

    mqttTimeout = setTimeout(() => {
      if (!resolved) {
        mqttResolved = true;
        cleanup();
        resolve({ data: oddsData, raceStatuses, reason: oddsData ? 'ok' : 'timeout' });
      }
    }, RACE_TIMEOUT);

    cleanupFns.push(() => { clearTimeout(mqttTimeout); });

    try {
      mqttClient = mqtt.connect(MQTT_URL, MQTT_OPTS);

      mqttClient.on('connect', () => {
        mqttClient.subscribe('racing/#', { qos: 0 }, (err) => {
          if (err) console.error(`[MQTT] Subscribe error: ${err.message}`);
        });
      });

      mqttClient.on('message', (topic, message) => {
        if (mqttResolved) return;
        try {
          const payload = JSON.parse(message.toString());
          const topicParts = topic.split('/');
          const topicRaceNo = topicParts[topicParts.length - 1]?.replace('R', '') || '';
          if (String(topicRaceNo) !== String(raceNo)) return;

          const rawOdds = extractOddsFromMQTT(payload, raceNo);
          if (rawOdds && (Object.keys(rawOdds.win || {}).length > 0 || Object.keys(rawOdds.place || {}).length > 0)) {
            mqttResolved = true;
            oddsData = rawOdds;
            clearTimeout(mqttTimeout);
            cleanup();
            resolve({ data: rawOdds, raceStatuses, reason: 'ok' });
          }
        } catch (e) {}
      });

      mqttClient.on('error', (err) => {
        // Don't resolve on error — only mqttTimeout or mqtt message should resolve.
        console.error(`[MQTT] Error: ${err.message}`);
      });

      mqttClient.on('close', () => {
        // Don't resolve on close — mqttTimeout handles the timeout case.
      });
    } catch (e) {
      clearTimeout(mqttTimeout);
      resolve({ data: oddsData, raceStatuses, reason: 'timeout' });
    }
  });

  // Race both: first to resolve wins
  const result = await Promise.race([graphqlPromise, mqttPromise]);
  cleanupFns.forEach(fn => { try { fn(); } catch (e) {} });
  if (mqttClient) { try { mqttClient.end(true); } catch (e) {} }

  return result;
}


// ─── Parse odds ────────────────────────────────────────────────────────────
// Handles both MQTT direct format ({ win: {}, place: {} }) and GraphQL format (nested)
function parseOdds(data) {
  // Direct format from MQTT: { win: { '1': 1.2 }, place: { '1': 1.1 } }
  if (data && (data.win || data.place)) {
    return {
      win: data.win || {},
      place: data.place || {}
    };
  }
  // GraphQL format: data.data.raceMeetings[0].pmPools
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

// Suppress Playwright CDP errors when browser/page is closed mid-flight.
// These are benign — they occur when page.close() disposes the CDP context
// while an async response handler is still in-flight.
process.on('uncaughtException', (err) => {
  if (err.message && err.message.includes('disposeBrowserContext')) return;
  console.error('Uncaught exception:', err.message);
});

// ─── Scrape all races — sequential, fresh browser per race ─────────────────────
// Each race gets its own Chromium instance to eliminate CDP context-sharing bugs.
// A shared browser causes page.on('response') handlers from previous races to fire
// on the next race's page, making all races return the first race's odds.
async function scrapeAllRaces(date, venue, races, total) {
  const raceResults = [];

  for (let i = 0; i < races.length; i++) {
    const raceNo = races[i];
    const raceId = buildRaceId(date, venue, raceNo);
    let browser = null;

    // Launch fresh browser for this race
    console.error(`[SCRAPE] race=${raceNo} launching browser...`);
    try {
      browser = await chromium.launch({ headless: true });
      console.error(`[SCRAPE] race=${raceNo} browser launched OK`);
    } catch (e) {
      console.error(`[SCRAPE] race=${raceNo} browser-launch-failed: ${e.message.slice(0,80)}`);
      raceResults.push({ raceNo, status: 'no-data', reason: 'browser-launch-failed', data: null });
      continue;
    }

    try {
      if (finishedRaces.has(raceId)) {
        console.log(`  Race ${raceNo}/${total}... ⏭`);
        raceResults.push({ raceNo, status: 'finished', data: null });
        continue;
      }

    process.stdout.write(`  Race ${raceNo}/${total}... `);
    const startRace = Date.now();
    const { data, raceStatuses, reason } = await fetchRaceOdds(browser, date, venue, raceNo);
    console.error(`[SCRAPE] race=${raceNo} elapsed=${Date.now()-startRace}ms reason=${reason}`);

      if (isRaceFinished(null, date, venue, raceNo, raceStatuses)) {
        console.log('⏭');
        raceResults.push({ raceNo, status: 'finished', data: null });
        continue;
      }

      if (!data) {
        console.log(`❌(${reason})`);
        raceResults.push({ raceNo, status: 'no-data', reason, data: null });
        continue;
      }

      const odds = parseOdds(data);
      if (!odds || (Object.keys(odds.win).length === 0 && Object.keys(odds.place).length === 0)) {
        console.log(`❌(no-pools)`);
        raceResults.push({ raceNo, status: 'no-odds', reason: 'no-pools', data: null });
        continue;
      }

      const scratchedHorses = [];
      const raceInfo = raceStatuses?.find(r => String(r.no) === String(raceNo));
      if (raceInfo?.runners) {
        raceInfo.runners.forEach(runner => {
          if (runner.status === 'Scratched') scratchedHorses.push(Number(runner.no));
        });
      }
      raceScratched[raceId] = scratchedHorses;

      const result = {
        race_id: raceId, date, venue,
        race_no: parseInt(raceNo),
        win: Object.fromEntries(Object.entries(odds.win).map(([k, v]) => [Number(k), v])),
        place: Object.fromEntries(Object.entries(odds.place).map(([k, v]) => [Number(k), v])),
        scratched: scratchedHorses,
        scraped_at: new Date()
      };
      console.log('✅');
      raceResults.push({ raceNo, status: 'ok', data: result });
    } finally {
      // Do NOT call browser.close() — Chromium cleans up automatically when this
      // function returns. Calling browser.close() races with page.close() in
      // cleanup() (both dispose the same CDP context), causing crashes.
    }
  }

  const successful = raceResults
    .filter(r => r.status === 'ok' && r.data)
    .map(r => r.data);

  const byReason = {};
  raceResults.forEach(r => {
    if (r.status === 'finished') return;
    if (r.status === 'ok') return;
    byReason[r.reason] = (byReason[r.reason] || 0) + 1;
  });
  const failureParts = Object.entries(byReason).map(([k, v]) => `${k}×${v}`);
  const finished = raceResults.filter(r => r.status === 'finished').length;

  if (failureParts.length > 0) {
    log(`[${new Date().toLocaleTimeString()}] ⚠️  Partial: ${failureParts.join(', ')}${finished > 0 ? ` (${finished} finished)` : ''}`);
  }

  return successful;
}

// ─── Check if race has results ───────────────────────────────────────────────
// raceStatuses can come directly from fetchRaceOdds result (avoids re-extraction)
function isRaceFinished(data, date, venue, raceNo, raceStatuses) {
  const raceId = buildRaceId(date, venue, raceNo);
  // Prefer passed raceStatuses, then try extracting from data (GraphQL format)
  const races = raceStatuses || data?.data?.raceMeetings?.[0]?._raceStatuses;
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
  try {
    const db = await getMongo();
    const result = await db.collection('live_odds').insertMany(
      docs.map(d => ({ ...d, scraped_at: new Date() }))
    );
    return result.insertedCount;
  } catch (e) {
    console.error('[MongoDB] Save error:', e.message);
    return 0;
  }
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
    const scrapeDate = raceDayResult.raceDate || process.env.RACE_DATE || today;
    log(`[${new Date().toLocaleTimeString()}] 🚀 Scraping ${venue} races [${races.join(', ')}]${finished > 0 ? ` (${finished} finished)` : ''}`);

    await sessionStart(races.map(r => ({ race_id: buildRaceId(scrapeDate, venue, r) })));

    // Wrap entire scrape in a hard timeout — if it takes > 12s, abort and don't block scheduleNext
    const scrapeResult = await Promise.race([
      scrapeAllRaces(scrapeDate, venue, races, total),
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
      await broadcastBatch(scrapeResult, races.map(r => buildRaceId(scrapeDate, venue, r)));
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
║   Race day:     scrape every 20 seconds            ║
║   Non-race day: scrape once if > 12h since last    ║
║   Skip if:     < 5s since last or scrape in prog   ║
║   Backoff:     5→10→20→40→60s on consecutive fails ║
║   Per-race:    12s timeout (sequential, 9 races)   ║
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
