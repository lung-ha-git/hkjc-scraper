const express = require('express');
const cors = require('cors');
const { MongoClient } = require('mongodb');

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json());

const mongoUrl = 'mongodb://localhost:27017/';
const dbName = 'hkjc_racing_dev';

let db;

async function connect() {
  const client = new MongoClient(mongoUrl);
  await client.connect();
  db = client.db(dbName);
  console.log('Connected');
}
connect().catch(console.error);

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
  
  // Add jersey_url to each entry
  for (const entry of entries) {
    const horse = await db.collection('horses').findOne({ name: entry.horse_name });
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

app.listen(PORT, () => console.log('Server:', PORT));

// Save AI prediction
app.post('/api/predictions', async (req, res) => {
  try {
    const { race_date, race_no, venue, predictions, weights, model_version, created_at } = req.body;
    
    const doc = {
      race_date,
      race_no,
      venue,
      predictions, // Array of { horse_no, horse_name, score, predicted_rank }
      weights,     // Object of factor weights
      model_version: model_version || 'v1.0.0',
      created_at: created_at || new Date().toISOString()
    };
    
    await db.collection('predictions').insertOne(doc);
    res.json({ success: true });
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
