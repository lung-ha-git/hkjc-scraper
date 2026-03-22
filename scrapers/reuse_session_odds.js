/**
 * HKJC Live Odds - Fast Version (Final)
 * 
 * Listener attached BEFORE navigation for reliable interception
 * 
 * Usage:
 *   node reuse_session_odds.js [date] [venue] [races...]
 *   node reuse_session_odds.js 2026-03-22 ST ALL
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');

const MONGODB_URI = 'mongodb://localhost:27017/';
const DB_NAME = 'hkjc_racing_dev';

/**
 * Fetch odds by intercepting network response
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
 * Parse odds
 */
function parseOdds(data, date, venue, raceNo) {
  if (!data?.data?.raceMeetings?.[0]?.pmPools) return null;
  
  const meeting = data.data.raceMeetings[0];
  const result = {
    race_id: `${date.replace(/-/g, '_')}_${venue}_${raceNo}`,
    date,
    venue,
    race_no: parseInt(raceNo),
    scraped_at: new Date(),
    odds: { WIN: [], PLA: [] }
  };
  
  meeting.pmPools?.forEach(pool => {
    if (pool.oddsType === 'WIN' || pool.oddsType === 'PLA') {
      pool.oddsNodes?.forEach(node => {
        result.odds[pool.oddsType].push({
          horse_no: node.combString,
          odds: parseFloat(node.oddsValue),
          hot: node.hotFavourite || false
        });
      });
    }
  });
  
  return result;
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
    console.log(`💾 Saved ${result.insertedCount} to MongoDB`);
    return result;
  } finally {
    await client.close();
  }
}

/**
 * Main
 */
async function main() {
  const args = process.argv.slice(2);
  const date = args[0] || '2026-03-22';
  const venue = args[1] || 'ST';
  let races = args.slice(2);
  
  if (races.length === 1 && races[0] === 'ALL') {
    races = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10'];
  }
  
  console.log(`\n🎯 Fast Mode: Fetching ${races.length} races...\n`);
  
  const browser = await chromium.launch({ 
    headless: true,
    channel: 'chrome'
  });
  
  const page = await browser.newPage();
  
  // Attach listener FIRST before any navigation
  const allData = [];
  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
    
    try {
      const body = await response.text();
      if (!body.includes('"pmPools"') || !body.includes('"oddsNodes"')) return;
      
      const json = JSON.parse(body);
      if (!json?.data?.raceMeetings?.[0]?.pmPools) return;
      
      allData.push(json);
    } catch (e) {}
  });
  
  // Establish session
  console.log('🔐 Establishing session...');
  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });
  await page.waitForTimeout(3000);
  console.log('✅ Session ready\n');
  
  const startTime = Date.now();
  const results = [];
  
  // Fetch all races
  for (const raceNo of races) {
    const data = await fetchRaceOdds(page, date, venue, raceNo);
    if (data) {
      const parsed = parseOdds(data, date, venue, raceNo);
      if (parsed) {
        results.push(parsed);
        const winTop = parsed.odds.WIN.slice(0, 2).map(h => `${h.horse_no}=${h.odds}`).join(',');
        console.log(`  ✅ Race ${raceNo}: WIN [${winTop}]`);
        continue;
      }
    }
    console.log(`  ❌ Race ${raceNo}: Failed`);
  }
  
  await browser.close();
  
  const elapsed = Date.now() - startTime;
  console.log(`\n⏱️  Fetched ${results.length}/${races.length} races in ${elapsed}ms`);
  
  if (results.length > 0) {
    await saveToMongoDB(results);
  }
  
  console.log('\n✅ Done!\n');
}

main().catch(console.error);
