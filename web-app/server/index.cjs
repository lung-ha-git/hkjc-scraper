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

const mongoUrl = 'mongodb://localhost:27017/';
const dbName = 'hkjc_racing_dev';

let db;

// In-memory cache for latest odds per race
// { "2026-03-22_ST_R7": { 1: { win, place, timestamp }, ... } }
const oddsCache = {};

// In-memory session tracking per race
// { "2026-03-22_ST_R7": { started_at: timestamp, finished_at: null } }
const oddsSessions = {};

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
  .then(() => {
    httpServer.listen(PORT, () => console.log('Server:', PORT));
  })
  .catch((err) => {
    console.error('MongoDB connection failed:', err.message);
    // Retry after 5s instead of crashing
    setTimeout(() => {
      console.log('Retrying MongoDB connection...');
      connect()
        .then(() => httpServer.listen(PORT, () => console.log('Server (retry):', PORT)))
        .catch(e => console.error('Retry also failed:', e.message));
    }, 5000);
  });

app.get('/api/health', (req, res) => res.json({ok: 1}));

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
  const entries = await db.collection('racecard_entries')
    .find(query)
    .toArray();
  
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
  res.json({ ok: 1, session: oddsSessions[race_id] || null });
});

// Session: GET /api/odds/session/:raceId — get session info
app.get('/api/odds/session/:raceId', (req, res) => {
  const { raceId } = req.params;
  res.json({ ok: 1, session: oddsSessions[raceId] || null });
});

// Batch broadcast: receive all races at once, emit to each race room
// Body: { races: [{ race_id, odds: { horse_no: { win, place } } }] }
app.post('/api/odds/batch-snapshot', (req, res) => {
  const { races } = req.body;
  if (!races || !Array.isArray(races)) {
    return res.status(400).json({ error: 'races array required' });
  }

  const timestamp = Date.now();
  let count = 0;

  races.forEach(({ race_id, odds }) => {
    if (!race_id || !odds) return;

    // Update cache
    const cached = {};
    Object.entries(odds).forEach(([horse_no, odds_val]) => {
      cached[Number(horse_no)] = { ...odds_val, updated_at: timestamp };
    });
    req.oddsCache[race_id] = cached;

    // Broadcast to race room (with session info)
    req.io.to(race_id).emit('odds_snapshot', {
      odds: cached,
      session: oddsSessions[race_id] || null
    });
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

// ML Prediction using XGBoost model with optional boosting
app.get('/api/predict', async (req, res) => {
  const { race_date, race_no, venue, boosting } = req.query;
  
  if (!race_date || !race_no) {
    return res.status(400).json({error: 'race_date and race_no required'});
  }
  
  try {
    const { execSync } = require('child_process');
    
    const boostingArg = boosting ? `'${boosting.replace(/'/g, "'\\''")}'` : 'null';
    const cmd = `python3 /Users/fatlung/.openclaw/workspace-main/hkjc_project/predict_xgb.py ${race_date} ${race_no} ${venue} ${boostingArg} 2>&1 | grep -v '^Loading'`;
    
    const result = execSync(cmd, { encoding: 'utf8', timeout: 60000 });
    
    res.json(JSON.parse(result));
  } catch (error) {
    console.error('Prediction error:', error.message);
    res.status(500).json({ error: error.message });
  }
});
