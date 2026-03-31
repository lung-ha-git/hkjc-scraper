/**
 * FEAT-012: Hybrid Odds Scraper
 * 
 * Features:
 * - Change-based writes (only when odds actually change)
 * - Periodic snapshots (every 30s for sparkline continuity)
 * - Race-aware auto start/stop
 * - API controllable via /api/scraper/start and /api/scraper/stop
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');
const http = require('http');

const MONGODB_URI = 'mongodb://localhost:27017/';
const DB_NAME = 'hkjc_racing_dev';
const API_BASE = 'http://localhost:3001';

// Configuration
const PERIODIC_SNAPSHOT_INTERVAL_MS = 30000;
const CHANGE_DETECTION_INTERVAL_MS = 10000;

// State
const state = {
  isRunning: false,
  currentRaces: new Map(),
  browser: null,
  page: null,
  lastPeriodicSnapshot: 0,
  stats: { changeWrites: 0, periodicWrites: 0, skippedWrites: 0, startTime: null },
  // FEAT-012.1 & 12.2: Race detection
  detectionMode: 'manual', // 'manual' | 'auto-detect'
  activeRaceDetectionInterval: null,
  raceEndDetectionInterval: null
};

function buildRaceId(date, venue, raceNo) {
  return `${date}_${venue}_R${raceNo}`;
}

// MongoDB Operations
async function saveChange(doc) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const collection = client.db(DB_NAME).collection('live_odds_changes');
    await collection.insertOne({ ...doc, is_change: true, scraped_at: new Date() });
    state.stats.changeWrites++;
  } finally { await client.close(); }
}

async function savePeriodicSnapshot(docs) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const collection = client.db(DB_NAME).collection('live_odds');
    const result = await collection.insertMany(docs.map(d => ({ ...d, is_periodic: true, scraped_at: new Date() })));
    state.stats.periodicWrites += result.insertedCount;
  } finally { await client.close(); }
}

async function cleanupOldRecords(hours = 24) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const db = client.db(DB_NAME);
    const cutoff = new Date(Date.now() - hours * 60 * 60 * 1000);
    const changes = await db.collection('live_odds_changes').deleteMany({ scraped_at: { $lt: cutoff } });
    const snapshots = await db.collection('live_odds').deleteMany({ scraped_at: { $lt: cutoff } });
    console.log(`[cleanup] Removed ${changes.deletedCount} changes + ${snapshots.deletedCount} snapshots`);
  } finally { await client.close(); }
}

// FEAT-012.1 & 12.2: Race Start/End Detection
async function detectTodayFixture() {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const db = client.db(DB_NAME);
    const today = new Date().toISOString().split('T')[0];
    const fixture = await db.collection('fixtures').findOne({ date: today });
    return fixture;
  } finally { await client.close(); }
}

async function checkRaceHasOdds(date, venue, raceNo) {
  // Quick check if odds exist for this race
  const data = await fetchRaceOdds(state.page, date, venue, raceNo);
  const odds = parseOdds(data);
  return odds && (Object.keys(odds.win).length > 0 || Object.keys(odds.place).length > 0);
}

async function checkRaceHasResults(date, venue, raceNo) {
  const client = new MongoClient(MONGODB_URI);
  try {
    await client.connect();
    const db = client.db(DB_NAME);
    const raceId = `${date.replace(/-/g, '_')}_${venue}_${raceNo}`;
    const race = await db.collection('races').findOne({ race_id: raceId });
    return race && race.results && race.results.length > 0;
  } finally { await client.close(); }
}

async function startRaceDetection() {
  // FEAT-012.1: Auto-detect when odds appear
  console.log('[detection] Starting race start detection...');
  
  const fixture = await detectTodayFixture();
  if (!fixture) {
    console.log('[detection] No fixture found for today');
    return;
  }
  
  const { date, venue, race_count = 10 } = fixture;
  console.log(`[detection] Today: ${date} ${venue}, ${race_count} races`);
  
  // Check each race every minute
  state.activeRaceDetectionInterval = setInterval(async () => {
    for (let raceNo = 1; raceNo <= race_count; raceNo++) {
      const raceId = buildRaceId(date, venue, raceNo);
      
      // Skip if already tracking
      if (state.currentRaces.has(raceId)) continue;
      
      // Check if odds available
      const hasOdds = await checkRaceHasOdds(date, venue, raceNo);
      if (hasOdds) {
        console.log(`[detection] 🔥 Race ${raceId} odds appeared! Auto-starting...`);
        await addRace(date, venue, raceNo);
      }
    }
  }, 60000); // Check every minute
}

async function startRaceEndDetection() {
  // FEAT-012.2: Auto-detect when race ends (results published)
  console.log('[detection] Starting race end detection...');
  
  state.raceEndDetectionInterval = setInterval(async () => {
    for (const [raceId, race] of state.currentRaces) {
      const hasResults = await checkRaceHasResults(race.date, race.venue, race.race_no);
      if (hasResults) {
        console.log(`[detection] 🏁 Race ${raceId} finished! Auto-stopping...`);
        await removeRace(raceId);
      }
    }
  }, 120000); // Check every 2 minutes
}

async function stopRaceDetection() {
  if (state.activeRaceDetectionInterval) {
    clearInterval(state.activeRaceDetectionInterval);
    state.activeRaceDetectionInterval = null;
  }
  if (state.raceEndDetectionInterval) {
    clearInterval(state.raceEndDetectionInterval);
    state.raceEndDetectionInterval = null;
  }
  console.log('[detection] Race detection stopped');
}

// Odds Detection
async function fetchRaceOdds(page, date, venue, raceNo) {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => { page.removeListener('response', handler); resolve(null); }, 8000);
    const handler = async (response) => {
      const url = response.url();
      if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
      try {
        const body = await response.text();
        if (!body.includes('"pmPools"')) return;
        const json = JSON.parse(body);
        if (!json?.data?.raceMeetings?.[0]?.pmPools) return;
        clearTimeout(timeout);
        page.removeListener('response', handler);
        resolve(json);
      } catch (e) {}
    };
    page.on('response', handler);
    page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/${raceNo}`, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
  });
}

function parseOdds(data) {
  if (!data?.data?.raceMeetings?.[0]?.pmPools) return null;
  const result = { win: {}, place: {} };
  data.data.raceMeetings[0].pmPools.forEach(pool => {
    const target = pool.oddsType === 'WIN' ? result.win : pool.oddsType === 'PLA' ? result.place : null;
    if (!target) return;
    pool.oddsNodes?.forEach(node => { target[node.combString] = parseFloat(node.oddsValue); });
  });
  return result;
}

function oddsChanged(prev, curr) {
  if (!prev || !curr) return true;
  return JSON.stringify(prev.win) !== JSON.stringify(curr.win) || JSON.stringify(prev.place) !== JSON.stringify(curr.place);
}

// Race Management
async function addRace(date, venue, raceNo) {
  const raceId = buildRaceId(date, venue, raceNo);
  if (state.currentRaces.has(raceId)) return false;
  state.currentRaces.set(raceId, { date, venue, race_no: parseInt(raceNo), race_id: raceId, lastOdds: null, startTime: Date.now(), changeCount: 0 });
  await sessionStart(raceId);
  console.log(`[scraper] Added race ${raceId}`);
  return true;
}

async function removeRace(raceId) {
  const race = state.currentRaces.get(raceId);
  if (!race) return false;
  if (race.lastOdds) {
    await savePeriodicSnapshot([{ race_id: raceId, date: race.date, venue: race.venue, race_no: race.race_no, win: race.lastOdds.win, place: race.lastOdds.place, is_final: true }]);
  }
  await sessionEnd(raceId);
  state.currentRaces.delete(raceId);
  console.log(`[scraper] Removed race ${raceId}`);
  return true;
}

// Session Tracking
async function sessionStart(raceId) {
  try { await fetch(`${API_BASE}/api/odds/session/start`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ race_id: raceId }) }); } catch (e) {}
}
async function sessionEnd(raceId) {
  try { await fetch(`${API_BASE}/api/odds/session/end`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ race_id: raceId }) }); } catch (e) {}
}
async function broadcastSnapshot(raceId, odds) {
  try {
    const normalized = {};
    for (const [h, v] of Object.entries(odds)) normalized[Number(h)] = v;
    await fetch(`${API_BASE}/api/odds/snapshot`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ race_id: raceId, odds: normalized }) });
  } catch (e) {}
}

// Core Loop
async function scrapeRace(race) {
  const { date, venue, race_no, race_id, lastOdds } = race;
  const data = await fetchRaceOdds(state.page, date, venue, race_no);
  if (!data) return null;
  const odds = parseOdds(data);
  if (!odds) return null;
  
  const changed = oddsChanged(lastOdds, odds);
  if (changed) {
    await saveChange({ race_id, date, venue, race_no, win: odds.win, place: odds.place, prev_win: lastOdds?.win || null, prev_place: lastOdds?.place || null });
    race.changeCount++;
    console.log(`[change] ${race_id}`);
  } else {
    state.stats.skippedWrites++;
  }
  
  race.lastOdds = odds;
  await broadcastSnapshot(race_id, odds);
  return odds;
}

async function runScrapingCycle() {
  if (!state.isRunning || state.currentRaces.size === 0) return;
  const now = Date.now();
  const isPeriodic = now - state.lastPeriodicSnapshot >= PERIODIC_SNAPSHOT_INTERVAL_MS;
  
  for (const [raceId, race] of state.currentRaces) {
    try { await scrapeRace(race); } catch (e) { console.error(`[error] ${raceId}: ${e.message}`); }
  }
  
  if (isPeriodic) {
    const snapshots = [];
    for (const [raceId, race] of state.currentRaces) {
      if (race.lastOdds) snapshots.push({ race_id: raceId, date: race.date, venue: race.venue, race_no: race.race_no, win: race.lastOdds.win, place: race.lastOdds.place });
    }
    if (snapshots.length > 0) {
      await savePeriodicSnapshot(snapshots);
      console.log(`[periodic] Saved ${snapshots.length} snapshots`);
    }
    state.lastPeriodicSnapshot = now;
  }
}

// Main Control
async function startScraper(options = {}) {
  if (state.isRunning) { console.log('[scraper] Already running'); return false; }
  const { date, venue, races, autoDetect = false } = options;
  
  console.log('\n🚀 FEAT-012: Hybrid Odds Scraper starting...');
  state.stats.startTime = Date.now();
  
  state.browser = await chromium.launch({ headless: true, channel: 'chrome' });
  state.page = await state.browser.newPage();
  
  // Get today's fixture if auto-detect
  let targetDate = date;
  let targetVenue = venue;
  
  if (autoDetect) {
    state.detectionMode = 'auto-detect';
    const fixture = await detectTodayFixture();
    if (fixture) {
      targetDate = fixture.date;
      targetVenue = fixture.venue;
      console.log(`[auto-detect] Today: ${targetDate} ${targetVenue}`);
    } else {
      console.log('[auto-detect] No fixture found, using defaults');
      targetDate = date || '2026-03-22';
      targetVenue = venue || 'ST';
    }
  } else {
    targetDate = date || '2026-03-22';
    targetVenue = venue || 'ST';
  }
  
  await state.page.goto(`https://bet.hkjc.com/ch/racing/wp/${targetDate}/${targetVenue}/1`, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await state.page.waitForTimeout(2000);
  
  if (autoDetect) {
    // FEAT-012.1: Start race start detection
    await startRaceDetection();
    // FEAT-012.2: Start race end detection  
    await startRaceEndDetection();
  } else if (races && races.length > 0) {
    for (const raceNo of races) await addRace(targetDate, targetVenue, raceNo);
  }
  
  state.isRunning = true;
  
  const loop = async () => { while (state.isRunning) { await runScrapingCycle(); await new Promise(r => setTimeout(r, CHANGE_DETECTION_INTERVAL_MS)); } };
  const cleanupLoop = async () => { while (state.isRunning) { await new Promise(r => setTimeout(r, 60 * 60 * 1000)); if (state.isRunning) await cleanupOldRecords(24); } };
  loop();
  cleanupLoop();
  
  console.log(`[scraper] Started with ${state.currentRaces.size} races (mode: ${state.detectionMode})`);
  return true;
}

async function stopScraper() {
  if (!state.isRunning) { console.log('[scraper] Not running'); return false; }
  console.log('\n🛑 Stopping scraper...');
  state.isRunning = false;
  
  // Stop detection intervals
  await stopRaceDetection();
  
  for (const [raceId] of state.currentRaces) await removeRace(raceId);
  if (state.browser) { await state.browser.close(); state.browser = null; state.page = null; }
  
  const duration = (Date.now() - state.stats.startTime) / 1000;
  console.log('\n📊 Stats:');
  console.log(`   Duration: ${duration.toFixed(1)}s`);
  console.log(`   Change writes: ${state.stats.changeWrites}`);
  console.log(`   Periodic writes: ${state.stats.periodicWrites}`);
  console.log(`   Skipped: ${state.stats.skippedWrites}`);
  return true;
}

// API Server
function startAPIServer(port = 3002) {
  const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.setHeader('Access-Control-Allow-Origin', '*');
    if (req.method === 'OPTIONS') { res.writeHead(200); res.end(); return; }
    
    const url = new URL(req.url, `http://localhost:${port}`);
    
    if (url.pathname === '/status' && req.method === 'GET') {
      res.writeHead(200);
      res.end(JSON.stringify({ isRunning: state.isRunning, races: Array.from(state.currentRaces.keys()), stats: state.stats }));
      return;
    }
    
    if (url.pathname === '/start' && req.method === 'POST') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const params = JSON.parse(body);
          const success = await startScraper({ 
            date: params.date, 
            venue: params.venue, 
            races: params.races,
            autoDetect: params.autoDetect 
          });
          res.writeHead(success ? 200 : 409);
          res.end(JSON.stringify({ 
            success, 
            races: Array.from(state.currentRaces.keys()),
            mode: state.detectionMode 
          }));
        } catch (e) { res.writeHead(500); res.end(JSON.stringify({ error: e.message })); }
      });
      return;
    }
    
    if (url.pathname === '/stop' && req.method === 'POST') {
      const success = await stopScraper();
      res.writeHead(200);
      res.end(JSON.stringify({ success, stats: state.stats }));
      return;
    }
    
    res.writeHead(404);
    res.end(JSON.stringify({ error: 'Not found' }));
  });
  
  server.listen(port, () => {
    console.log(`[api] Control server on port ${port}`);
    console.log(`[api] GET /status, POST /start, POST /stop`);
  });
  return server;
}

// Graceful Shutdown
function setupShutdown() {
  const shutdown = async (signal) => {
    console.log(`\n${signal} received, shutting down...`);
    if (state.isRunning) await stopScraper();
    process.exit(0);
  };
  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));
}

// CLI
const args = process.argv.slice(2);
const date = args[0];
const venue = args[1];
const racesArg = args.indexOf('--races');
const raceList = racesArg >= 0 ? args[racesArg + 1].split(',').map(Number) : [1,2,3,4,5,6,7,8,9,10];
const autoDetect = args.includes('--auto-detect');
const apiMode = args.includes('--api');

setupShutdown();

if (apiMode) {
  startAPIServer(3002);
} else if (autoDetect) {
  // FEAT-012.5: Auto-detect from fixtures
  startScraper({ autoDetect: true });
} else if (date && venue) {
  startScraper({ date, venue, races: raceList });
} else {
  console.log('\n🚀 FEAT-012: Hybrid Odds Scraper\n');
  console.log('Usage:');
  console.log('  node hybrid_odds_scraper.js <date> <venue> --races 1,2,3');
  console.log('  node hybrid_odds_scraper.js --auto-detect              # Auto mode');
  console.log('  node hybrid_odds_scraper.js --api                      # API server\n');
}

module.exports = { startScraper, stopScraper, startAPIServer, state };
