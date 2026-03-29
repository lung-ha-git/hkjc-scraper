const express = require('express');
const cors = require('cors');
const { MongoClient, ObjectId } = require('mongodb');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');

const app = express();
const PORT = 3001;

// Create HTTP server + Socket.IO
const httpServer = http.createServer(app);
const io = new Server(httpServer, {
  cors: {
    origin: '*',
    methods: ['GET', 'POST']
  }
});

app.use(cors());
app.use(express.json());

// Serve built static files from dist/
app.use(express.static(path.join(__dirname, '../dist')));

// SPA fallback: serve index.html for non-API, non-socket.io routes
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../dist/index.html'));
});

const mongoUrl = process.env.MONGODB_URI || 'mongodb://mongodb:27017/';
const dbName = process.env.MONGODB_DATABASE || 'horse_racing';

let db;

// In-memory cache for latest odds per race
// { "2026-03-22_ST_R7": { 1: { win, place, timestamp }, ... } }
const oddsCache = {};

// Preload odds cache from MongoDB on startup
async function preloadOddsCache() {
  try {
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
      // Broadcast to all connected clients for this race
      io.to(race._id).emit('odds_snapshot', {
        odds: cached,
        session: oddsSessions[race._id] || null
      });
    }
    console.log(`[preload] Loaded ${races.length} races into cache`);
  } catch (e) {
    console.error('[preload] Failed:', e.message);
  }
}

// In-memory session tracking per race
// { "2026-03-22_ST_R7": { started_at: timestamp, finished_at: null } }
const oddsSessions = {};

// Sweep interval: clean up finished/old races every 30 min
const CACHE_TTL_MS = 2 * 60 * 60 * 1000; // 2 hours after finished_at
const SWEEP_INTERVAL_MS = 30 * 60 * 1000;

function sweepOddsCache() {
  const now = Date.now();
  const before = Object.keys(oddsCache);
  let cleaned = 0;
  before.forEach(race_id => {
    const sess = oddsSessions[race_id];
    // Clean if: race has ended AND (no TTL or TTL exceeded)
    if (sess?.finished_at && (now - sess.finished_at > CACHE_TTL_MS)) {
      delete oddsCache[race_id];
      cleaned++;
    }
  });
  if (cleaned > 0) console.log(`[cache sweep] cleaned ${cleaned} races`);
}

// Start periodic sweep
setInterval(sweepOddsCache, SWEEP_INTERVAL_MS);

io.on('connection', (socket) => {
  console.log('[WS] Client connected:', socket.id);

  socket.on('subscribe', ({ race_id }) => {
    if (!race_id) return;
    socket.join(race_id);
    console.log(`[WS] ${socket.id} joined ${race_id}`);
    
    // Send cached snapshot if available
    if (oddsCache[race_id]) {
      socket.emit('odds_snapshot', {
        odds: oddsCache[race_id],
        session: oddsSessions[race_id] || null
      });
    }
  });

  socket.on('unsubscribe', ({ race_id }) => {
    if (!race_id) return;
    socket.leave(race_id);
    console.log(`[WS] ${socket.id} left ${race_id}`);
  });

  socket.on('disconnect', () => {
    console.log('[WS] Client disconnected:', socket.id);
  });
});

// Expose io instance for scraper calls via /api/odds/broadcast
app.use((req, res, next) => {
  req.io = io;
  req.oddsCache = oddsCache;
  next();
});

async function connect() {
  const client = new MongoClient(mongoUrl);
  await client.connect();
  db = client.db(dbName);
  console.log('Connected');
}
connect()
  .then(async () => {
    await preloadOddsCache();  // ← 預加載 cache
    httpServer.listen(PORT, () => console.log('Server:', PORT));
  })
  .catch((err) => {
    console.error('MongoDB connection failed:', err.message);
    // Retry after 5s instead of crashing
    setTimeout(() => {
      console.log('Retrying MongoDB connection...');
      connect()
        .then(async () => {
          await preloadOddsCache();  // ← 修復：retry 時也預加載 cache
          httpServer.listen(PORT, () => console.log('Server (retry):', PORT));
        })
        .catch(e => console.error('Retry also failed:', e.message));
    }, 5000);
  });

app.get('/api/health', (req, res) => res.json({ok: 1}));
app.get('/health', (req, res) => res.json({ok: 1}));

// Fixtures - upcoming and past race days
app.get('/api/fixtures', async (req, res) => {
  const { mode = 'upcoming' } = req.query; // 'upcoming', 'past', or 'all'
  const today = new Date().toISOString().split('T')[0];
  
  let query = {};
  if (mode === 'upcoming') {
    query = { date: { $gte: today } };
  } else if (mode === 'past') {
    query = { date: { $lt: today } };
  }
  
  const fixtures = await db.collection('fixtures')
    .find(query)
    .sort({ date: mode === 'past' ? -1 : 1 })
    .limit(20)
    .toArray();
  
  res.json(fixtures);
});

// Racecards - for a specific race day
app.get('/api/racecards', async (req, res) => {
  const { date, venue } = req.query;
  
  if (!date) {
    return res.status(400).json({error: 'date required'});
  }
  
  const query = { race_date: date };
  if (venue) query.venue = venue;
  
  const racecards = await db.collection('racecards')
    .find(query)
    .sort({ race_no: 1 })
    .toArray();
  
  // Get horse entries
  let entries = await db.collection('racecard_entries')
    .find(query)
    .toArray();
  
  // Fallback: if racecard_entries is empty, extract from racecards' embedded horses
  if (entries.length === 0 && racecards.length > 0) {
    entries = [];
    for (const rc of racecards) {
      if (rc.horses && Array.isArray(rc.horses)) {
        for (const horse of rc.horses) {
          // Skip standby/non-declared horses (horse_no=0 or status=Standby)
          if (horse.status === 'Standby' || horse.horse_no === 0 || horse.horse_no === '0') {
            continue;
          }
          entries.push({
            ...horse,
            race_date: rc.race_date,
            race_no: rc.race_no,
            venue: rc.venue,
          });
        }
      }
    }
  }
  
  // Add jersey_url to each entry (lookup by hkjc_horse_id)
  for (const entry of entries) {
    const horse = await db.collection('horses').findOne({ hkjc_horse_id: entry.hkjc_horse_id });
    entry.jersey_url = horse?.jersey_url || null;
  }
  
  res.json({ racecards, entries });
});

app.get('/api/races', async (req, res) => {
  const { date } = req.query;
  console.log('Query date:', date);
  const query = date ? { race_date: date } : {};
  console.log('Query:', query);
  const r = await db.collection('races').find(query).sort({ race_date: -1, race_no: 1 }).limit(50).toArray();
  console.log('Found:', r.length, 'races');
  res.json(r);
});

// Get latest cached odds for a race (HTTP fallback / initial load)
app.get('/api/odds/:raceId', (req, res) => {
  const { raceId } = req.params;
  const cached = req.oddsCache[raceId];
  if (cached) {
    res.json({ odds: cached, source: 'cache' });
  } else {
    res.json({ odds: {}, source: 'cache' });
  }
});

// Broadcast odds update (called by scraper after writing to MongoDB)
// Body: { race_id, horse_no, win, place }
app.post('/api/odds/broadcast', (req, res) => {
  const { race_id, horse_no, win, place } = req.body;
  if (!race_id || horse_no == null) {
    return res.status(400).json({ error: 'race_id and horse_no required' });
  }

  const timestamp = Date.now();

  // Update in-memory cache
  if (!req.oddsCache[race_id]) {
    req.oddsCache[race_id] = {};
  }
  req.oddsCache[race_id][Number(horse_no)] = { win, place, updated_at: timestamp };

  // Broadcast to all subscribers of this race
  req.io.to(race_id).emit('odds_update', {
    horse_no: Number(horse_no),
    win,
    place,
    timestamp
  });

  res.json({ ok: 1, broadcast: true });
});

// Broadcast full snapshot (called by scraper on initial scrape)
// Body: { race_id, odds: { horse_no: { win, place } } }
app.post('/api/odds/snapshot', (req, res) => {
  const { race_id, odds } = req.body;
  if (!race_id || !odds) {
    return res.status(400).json({ error: 'race_id and odds required' });
  }

  const timestamp = Date.now();

  // Update cache
  const cached = {};
  Object.entries(odds).forEach(([horse_no, odds_val]) => {
    cached[Number(horse_no)] = { ...odds_val, updated_at: timestamp };
  });
  req.oddsCache[race_id] = cached;

  // Broadcast snapshot
  req.io.to(race_id).emit('odds_snapshot', {
    odds: cached,
    session: oddsSessions[race_id] || null
  });

  res.json({ ok: 1, count: Object.keys(odds).length });
});

// Session: POST /api/odds/session/start — record scraping start time
// Body: { race_id }
app.post('/api/odds/session/start', (req, res) => {
  const { race_id } = req.body;
  if (!race_id) return res.status(400).json({ error: 'race_id required' });
  if (!oddsSessions[race_id]) {
    oddsSessions[race_id] = { started_at: Date.now(), finished_at: null };
  }
  res.json({ ok: 1, session: oddsSessions[race_id] });
});

// Session: POST /api/odds/session/end — record scraping end time
// Body: { race_id }
app.post('/api/odds/session/end', (req, res) => {
  const { race_id } = req.body;
  if (!race_id) return res.status(400).json({ error: 'race_id required' });
  if (oddsSessions[race_id]) {
    oddsSessions[race_id].finished_at = Date.now();
    req.io.to(race_id).emit('odds_session_end', { session: oddsSessions[race_id] });
  }
  // Clean up oddsCache immediately on race end
  if (oddsCache[race_id]) {
    delete oddsCache[race_id];
    console.log(`[cache] removed ${race_id} on session end`);
  }
  res.json({ ok: 1, session: oddsSessions[race_id] || null });
});

// Cache: POST /api/odds/cache/sweep — manual cache cleanup
app.post('/api/odds/cache/sweep', (req, res) => {
  const before = Object.keys(oddsCache).length;
  sweepOddsCache();
  const after = Object.keys(oddsCache).length;
  res.json({ ok: 1, before, after, freed: before - after });
});

// Cache: GET /api/odds/cache/stats — show cache size
app.get('/api/odds/cache/stats', (req, res) => {
  const races = Object.keys(oddsCache);
  res.json({
    ok: 1,
    races_count: races.length,
    races: races.map(id => ({ race_id: id, horses_count: Object.keys(oddsCache[id] || {}).length }))
  });
});

// Session: GET /api/odds/session/:raceId — get session info
app.get('/api/odds/session/:raceId', (req, res) => {
  const { raceId } = req.params;
  res.json({ ok: 1, session: oddsSessions[raceId] || null });
});

// Batch broadcast: receive all races at once, emit to each race room
// Body: { races: [{ race_id, odds: { horse_no: { win, place } }, scratched: [horse_no] }] }
app.post('/api/odds/batch-snapshot', (req, res) => {
  const { races } = req.body;
  if (!races || !Array.isArray(races)) {
    return res.status(400).json({ error: 'races array required' });
  }

  const timestamp = Date.now();
  let count = 0;

  races.forEach(({ race_id, odds, scratched }) => {
    if (!race_id) return;

    // Update odds cache if present
    if (odds && Object.keys(odds).length > 0) {
      const cached = {};
      Object.entries(odds).forEach(([horse_no, odds_val]) => {
        cached[Number(horse_no)] = { ...odds_val, updated_at: timestamp };
      });
      req.oddsCache[race_id] = cached;
    }

    // Always broadcast scratched horses (even for RESULT races with no odds)
    if (scratched && scratched.length > 0) {
      req.io.to(race_id).emit('odds_snapshot', {
        odds: req.oddsCache[race_id] || {},
        scratched: scratched,
        session: oddsSessions[race_id] || null
      });
    } else if (odds && Object.keys(odds).length > 0) {
      req.io.to(race_id).emit('odds_snapshot', {
        odds: req.oddsCache[race_id] || {},
        scratched: scratched || [],
        session: oddsSessions[race_id] || null
      });
    }
    count++;
  });

  res.json({ ok: 1, races_count: count });
});

// Get full odds history from MongoDB for a race
// Returns: { times: [...], horses: { [horseNo]: { win: [...], place: [...] } } }
app.get('/api/odds/history/:raceId', async (req, res) => {
  const { raceId } = req.params;
  
  const docs = await db.collection('live_odds')
    .find({ race_id: raceId })
    .sort({ scraped_at: 1 })
    .toArray();
  
  if (!docs.length) return res.json({ times: [], horses: {} });
  
  // Collect all horse numbers across all docs (normalize to string)
  const allHorses = new Set();
  docs.forEach(doc => {
    Object.keys(doc.win || {}).forEach(k => allHorses.add(String(Number(k))));
    Object.keys(doc.place || {}).forEach(k => allHorses.add(String(Number(k))));
  });
  
  // Build time series per horse (keyed by string: "1", "2", ... "14")
  const horses = {};
  Array.from(allHorses).sort((a, b) => Number(a) - Number(b)).forEach(h => {
    horses[h] = { win: [], place: [] };
  });
  
  const times = docs.map(d => d.scraped_at);
  
  docs.forEach(doc => {
    Object.entries(doc.win || {}).forEach(([hk, v]) => {
      const h = String(Number(hk));
      if (horses[h]) horses[h].win.push(v);
    });
    Object.entries(doc.place || {}).forEach(([hk, v]) => {
      const h = String(Number(hk));
      if (horses[h]) horses[h].place.push(v);
    });
  });
  
  res.json({ times, horses });
});

app.get('/api/horses/best-times', async (req, res) => {
  const { date, raceNo } = req.query;
  console.log('best-times called', date, raceNo);
  
  const race = await db.collection('races').findOne({ race_date: date, race_no: parseInt(raceNo) });
  if (!race || !race.results) return res.json({});
  
  const bestTimes = {};
  
  for (const hr of race.results) {
    const horse = await db.collection('horses').findOne({ name: hr.horse_name });
    if (!horse) continue;
    
    const history = await db.collection('horse_race_history')
      .find({ hkjc_horse_id: horse.hkjc_horse_id })
      .sort({ finish_time: 1 })
      .limit(1)
      .toArray();
    
    if (history.length > 0 && history[0].finish_time) {
      bestTimes[hr.horse_name] = history[0].finish_time;
    }
  }
  
  res.json(bestTimes);
});

// Save AI prediction
app.post('/api/predictions', async (req, res) => {
  try {
    const { race_date, race_no, venue, predictions, weights, boosting, racecard, model_version, created_at } = req.body;
    
    const doc = {
      race_date,
      race_no,
      venue,
      predictions,
      weights,
      model_version: model_version || 'v1.0.0',
      created_at: created_at || new Date().toISOString()
    };
    
    await db.collection('predictions').insertOne(doc);
    
    // Save boost experiment if boosting is non-default
    const isDefault = !boosting || Object.values(boosting).every(v => v === 1.0);
    if (!isDefault && racecard) {
      const experiment = {
        race_date,
        race_no,
        venue,
        boosting,
        racecard,
        predictions: predictions.map(p => ({
          horse_name: p.horse_name,
          predicted_rank: p.predicted_rank,
          score: p.score
        })),
        created_at: new Date().toISOString()
      };
      await db.collection('boost_experiments').insertOne(experiment);
    }
    
    res.json({ success: true, saved_experiment: !isDefault });
  } catch (error) {
    console.error('Error saving prediction:', error);
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/horses/by-name/:name', async (req, res) => {
  const { name } = req.params;
  const horse = await db.collection('horses').findOne({ name: name });
  if (!horse) return res.status(404).json({error: 'Not found'});
  res.json({name: horse.name, jersey_url: horse.jersey_url, current_rating: horse.current_rating});
});

// Get horse by horse_id (e.g., K290)
app.get('/api/horses/by-id/:horseId', async (req, res) => {
  const { horseId } = req.params;
  const horse = await db.collection('horses').findOne({ hkjc_horse_id: horseId });
  if (!horse) return res.status(404).json({error: 'Not found'});
  res.json({
    name: horse.name, 
    jersey_url: horse.jersey_url, 
    current_rating: horse.current_rating,
    hkjc_horse_id: horse.hkjc_horse_id
  });
});

// Load model configuration
const MODEL_CONFIG_PATH = path.join(__dirname, '../../config/model-config.json');
let modelConfig = { models: {}, settings: {}, feature_flags: {} };

try {
  const configData = require('fs').readFileSync(MODEL_CONFIG_PATH, 'utf8');
  modelConfig = JSON.parse(configData);
  console.log('[ModelConfig] Loaded', Object.keys(modelConfig.models).length, 'models');
} catch (err) {
  console.warn('[ModelConfig] Could not load config, using defaults');
}

// Get available models
app.get('/api/models', (req, res) => {
  const models = Object.entries(modelConfig.models).map(([id, model]) => ({
    id,
    name: model.name,
    description: model.description,
    version: model.version,
    type: model.type,
    features: model.features,
    accuracy: model.accuracy,
    status: model.status,
    default: model.default || false
  }));
  
  res.json({
    models,
    default_model: modelConfig.settings?.default_model || 'xgb-default',
    settings: modelConfig.settings,
    feature_flags: modelConfig.feature_flags
  });
});

// Get current model configuration
app.get('/api/models/config', (req, res) => {
  res.json(modelConfig);
});

// ML Prediction with model switching support
app.get('/api/predict', async (req, res) => {
  const { race_date, race_no, venue, boosting, model } = req.query;
  
  if (!race_date || !race_no) {
    return res.status(400).json({error: 'race_date and race_no required'});
  }
  
  // Determine which model to use
  const modelId = model || modelConfig.settings?.default_model || 'xgb-default';
  const modelInfo = modelConfig.models[modelId];
  
  if (!modelInfo) {
    return res.status(400).json({error: `Unknown model: ${modelId}`});
  }
  
  if (modelInfo.status === 'disabled') {
    return res.status(400).json({error: `Model ${modelId} is disabled`});
  }
  
  try {
    const { execSync } = require('child_process');
    const fs = require('fs');
    
    // Construct script path (use /app for Docker container)
    const scriptPath = path.join('/app', modelInfo.script);
    
    // Check if script exists
    if (!fs.existsSync(scriptPath)) {
      // Fall back to default predictor if model script doesn't exist yet
      if (modelId !== 'xgb-default') {
        console.warn(`[Predict] Model script not found: ${scriptPath}, falling back to xgb-default`);
      }
    }
    
    const boostingArg = boosting ? `'${boosting.replace(/'/g, "'\\''")}'` : 'null';
    
    // Use model-specific script if available, otherwise use default
    let cmd;
    if (fs.existsSync(scriptPath) && modelInfo.script !== 'predict_xgb.py') {
      cmd = `python3 ${scriptPath} ${race_date} ${race_no} ${venue} ${boostingArg} 2>&1`;
    } else {
      // Default prediction using predict_xgb.py
      cmd = `python3 /app/predict_xgb.py ${race_date} ${race_no} ${venue} ${boostingArg} 2>/dev/null`;
    }
    
    const timeoutMs = (modelConfig.settings?.timeout_seconds || 60) * 1000;
    const result = execSync(cmd, { encoding: 'utf8', timeout: timeoutMs });
    
    const predictionData = JSON.parse(result);
    
    // Add model metadata to response
    predictionData.model_used = {
      id: modelId,
      name: modelInfo.name,
      version: modelInfo.version,
      type: modelInfo.type
    };
    
    res.json(predictionData);
  } catch (error) {
    console.error('Prediction error:', error.message);
    res.status(500).json({ 
      error: error.message,
      model_requested: modelId 
    });
  }
});

// FEAT-006: Racecard vs Actual Entries Validation API
// Get latest validation for a race day
app.get('/api/validations/:date/:venue', async (req, res) => {
  const { date, venue } = req.params;
  
  try {
    const validation = await db.collection('racecard_validations')
      .findOne(
        { date, venue },
        { sort: { validated_at: -1 } }
      );
    
    if (!validation) {
      return res.json({ has_changes: false, races: [], summary: null });
    }
    
    res.json({
      has_changes: validation.summary?.races_with_changes > 0,
      validated_at: validation.validated_at,
      summary: validation.summary,
      races: validation.races || []
    });
  } catch (error) {
    console.error('Validation API error:', error);
    res.status(500).json({ error: error.message });
  }
});

// Get validation for a specific race
app.get('/api/validations/:date/:venue/:raceNo', async (req, res) => {
  const { date, venue, raceNo } = req.params;
  
  try {
    const validation = await db.collection('racecard_validations')
      .findOne(
        { date, venue },
        { sort: { validated_at: -1 } }
      );
    
    if (!validation || !validation.races) {
      return res.json({ has_changes: false });
    }
    
    const race = validation.races.find(r => r.race_no === parseInt(raceNo));
    
    if (!race) {
      return res.json({ has_changes: false });
    }
    
    res.json({
      race_no: race.race_no,
      has_changes: race.has_changes,
      added: race.added || [],
      removed: race.removed || [],
      substituted: race.substituted || [],
      changed: race.changed || []
    });
  } catch (error) {
    console.error('Validation API error:', error);
    res.status(500).json({ error: error.message });
  }
});

// FEAT-012: Hybrid Scraper API endpoints
// Proxy to hybrid scraper control server (port 3002)
const HYBRID_SCRAPER_PORT = 3002;
const HYBRID_SCRAPER_HOST = 'localhost';

app.post('/api/scraper/start', async (req, res) => {
  try {
    const { date, venue, races } = req.body;
    if (!date || !venue || !races) {
      return res.status(400).json({ error: 'date, venue, and races required' });
    }
    
    const response = await fetch(`http://${HYBRID_SCRAPER_HOST}:${HYBRID_SCRAPER_PORT}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, venue, races })
    });
    
    const result = await response.json();
    res.status(response.status).json(result);
  } catch (error) {
    console.error('Scraper start error:', error);
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/scraper/stop', async (req, res) => {
  try {
    const response = await fetch(`http://${HYBRID_SCRAPER_HOST}:${HYBRID_SCRAPER_PORT}/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    
    const result = await response.json();
    res.status(response.status).json(result);
  } catch (error) {
    console.error('Scraper stop error:', error);
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/scraper/status', async (req, res) => {
  try {
    const response = await fetch(`http://${HYBRID_SCRAPER_HOST}:${HYBRID_SCRAPER_PORT}/status`);
    const result = await response.json();
    res.status(response.status).json(result);
  } catch (error) {
    console.error('Scraper status error:', error);
    res.status(500).json({ error: error.message });
  }
});

// Models download API
const fs = require('fs');

const MODELS_DIR = '/app/models';

// List all available models
app.get('/api/models/list', (req, res) => {
  try {
    if (!fs.existsSync(MODELS_DIR)) {
      return res.json({ models: [], updated: null });
    }
    
    const files = fs.readdirSync(MODELS_DIR);
    const models = files
      .filter(f => f.endsWith('.pkl') || f.endsWith('.json'))
      .map(f => {
        const filepath = path.join(MODELS_DIR, f);
        const stats = fs.statSync(filepath);
        return {
          name: f,
          size: stats.size,
          modified: stats.mtime.toISOString()
        };
      })
      .sort((a, b) => new Date(b.modified) - new Date(a.modified));
    
    // Get latest update time
    const updated = models.length > 0 ? models[0].modified : null;
    
    res.json({ models, updated });
  } catch (error) {
    console.error('Models list error:', error);
    res.status(500).json({ error: error.message });
  }
});

// Download a specific model file
app.get('/api/models/download/:filename', (req, res) => {
  const { filename } = req.params;
  
  // Security: only allow .pkl and .json files
  if (!filename.endsWith('.pkl') && !filename.endsWith('.json')) {
    return res.status(400).json({ error: 'Only .pkl and .json files allowed' });
  }
  
  const filepath = path.join(MODELS_DIR, filename);
  
  if (!fs.existsSync(filepath)) {
    return res.status(404).json({ error: 'Model not found' });
  }
  
  res.download(filepath, filename);
});

// ─── Logs download API ─────────────────────────────────────────────────────────
const PIPELINE_LOGS_DIR = '/app/logs/pipeline';
const ODDS_LOGS_DIR = '/app/scrapers/logs';

// List all available logs
app.get('/api/logs/list', (req, res) => {
  try {
    const logs = { pipeline: [], odds: [] };
    
    // Pipeline logs
    if (fs.existsSync(PIPELINE_LOGS_DIR)) {
      const pipelineFiles = fs.readdirSync(PIPELINE_LOGS_DIR)
        .filter(f => f.endsWith('.log') || f.endsWith('.json'))
        .map(f => {
          const stats = fs.statSync(path.join(PIPELINE_LOGS_DIR, f));
          return { source: 'pipeline', name: f, size: stats.size, modified: stats.mtime.toISOString() };
        });
      logs.pipeline = pipelineFiles.sort((a, b) => new Date(b.modified) - new Date(a.modified));
    }
    
    // Odds collector logs
    if (fs.existsSync(ODDS_LOGS_DIR)) {
      const oddsFiles = fs.readdirSync(ODDS_LOGS_DIR)
        .filter(f => f.endsWith('.log'))
        .map(f => {
          const filepath = path.join(ODDS_LOGS_DIR, f);
          const stats = fs.statSync(filepath);
          return { source: 'odds', name: f, size: stats.size, modified: stats.mtime.toISOString() };
        });
      logs.odds = oddsFiles.sort((a, b) => new Date(b.modified) - new Date(a.modified));
    }
    
    const allLogs = [...logs.pipeline, ...logs.odds].sort((a, b) => new Date(b.modified) - new Date(a.modified));
    
    res.json({ logs, updated: allLogs[0]?.modified || null });
  } catch (error) {
    console.error('Logs list error:', error);
    res.status(500).json({ error: error.message });
  }
});

// Download a specific log file
app.get('/api/logs/download/:source/:filename', (req, res) => {
  const { source, filename } = req.params;
  
  // Security: only allow .log and .json files
  if (!filename.endsWith('.log') && !filename.endsWith('.json')) {
    return res.status(400).json({ error: 'Only .log and .json files allowed' });
  }
  
  const baseDir = source === 'pipeline' ? PIPELINE_LOGS_DIR : ODDS_LOGS_DIR;
  const filepath = path.join(baseDir, filename);
  
  if (!fs.existsSync(filepath)) {
    return res.status(404).json({ error: 'Log not found' });
  }
  
  res.download(filepath, `${source}_${filename}`);
});
