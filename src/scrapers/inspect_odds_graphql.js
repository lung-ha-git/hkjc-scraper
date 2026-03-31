/**
 * FEAT-007 7.1 — Inspect full odds GraphQL response structure
 * Saves ALL GraphQL responses, focuses on raceMeetings with runners data.
 */

const { chromium } = require('playwright');
const fs = require('fs');

const DATE = process.argv[2] || '2026-03-22';
const VENUE = process.argv[3] || 'ST';
const RACE = process.argv[4] || '1';
const OUT_DIR = __dirname;

let count = 0;

async function main() {
  console.log(`\n🔍 Inspecting odds GraphQL: ${DATE} ${VENUE} R${RACE}\n`);
  console.log('Output files will be saved to:', OUT_DIR);

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();

  page.on('response', async (response) => {
    const url = response.url();
    const isGraphQL = url.includes('graphql') || url.includes('info.cld.hkjc.com');
    if (!isGraphQL) return;
    
    count++;
    const outfile = `${OUT_DIR}/graphql_${DATE}_${VENUE}_R${RACE}_resp${count}.json`;
    
    try {
      const body = await response.text();
      if (!body || body.length < 50) return;
      
      let json;
      try { json = JSON.parse(body); } catch { return; }
      
      fs.writeFileSync(outfile, JSON.stringify(json, null, 2));
      
      // Check if it has useful race data
      const hasRaceData = json?.data?.raceMeetings?.length > 0 ||
                          json?.data?.raceMeeting?.length > 0 ||
                          JSON.stringify(json).includes('"runners"');
      
      const marker = hasRaceData ? '🏁' : '  ';
      console.log(`${marker} [${count}] ${url.split('/').pop().substring(0,40)}... → ${outfile.split('/').pop()} (${body.length} bytes)${hasRaceData ? ' [HAS RACE DATA]' : ''}`);
      
      if (hasRaceData) {
        // Print structure
        printStructure(json);
      }
    } catch (e) {
      console.error(`[${count}] Error: ${e.message}`);
    }
  });

  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${DATE}/${VENUE}/${RACE}`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });

  await page.waitForTimeout(5000);
  await browser.close();
  console.log(`\n✅ Done — ${count} responses captured\n`);
}

function printStructure(json, depth = 0) {
  const indent = '  '.repeat(depth);
  
  if (json == null || typeof json !== 'object') {
    console.log(`${indent}= ${json}`);
    return;
  }
  
  if (Array.isArray(json)) {
    if (json.length === 0) {
      console.log(`${indent}[]`);
      return;
    }
    console.log(`${indent}[array x${json.length}]`);
    if (depth < 3) printStructure(json[0], depth + 1);
    return;
  }
  
  const keys = Object.keys(json);
  if (keys.length === 0) {
    console.log(`${indent}{}`);
    return;
  }
  
  console.log(`${indent}{${keys.length} keys}`);
  
  // Categorize keys
  const scalar = keys.filter(k => !Array.isArray(json[k]) && typeof json[k] !== 'object');
  const object = keys.filter(k => typeof json[k] === 'object' && json[k] !== null && !Array.isArray(json[k]));
  const arrays = keys.filter(k => Array.isArray(json[k]));
  
  if (depth < 2) {
    scalar.slice(0,5).forEach(k => console.log(`${indent}  ${k}= ${json[k]}`));
    arrays.slice(0,5).forEach(k => {
      const arr = json[k];
      const preview = arr.length > 0 
        ? (typeof arr[0] === 'object' ? `{${Object.keys(arr[0]).join(',')}} x${arr.length}` : JSON.stringify(arr[0]).substring(0,50))
        : '[]';
      console.log(`${indent}  ${k} [${arr.length}]: ${preview}`);
    });
    if (depth < 1 && arrays.includes('raceMeetings')) {
      const rm = json.raceMeetings[0];
      console.log(`\n${indent}=== raceMeetings[0] ===`);
      printMeeting(rm, depth + 1);
    }
  }
}

function printMeeting(meeting, depth = 1) {
  const indent = '  '.repeat(depth);
  if (!meeting) return;
  
  // Meeting level scalars
  const scalarFields = ['id','status','venueCode','date','totalNumberOfRace','currentNumberOfRace','dateOfWeek','meetingType'];
  scalarFields.forEach(f => {
    if (meeting[f] !== undefined) console.log(`${indent}  ${f}= ${meeting[f]}`);
  });
  
  // races array
  if (meeting.races && meeting.races.length > 0) {
    console.log(`\n${indent}  races [${meeting.races.length} races]:`);
    meeting.races.slice(0, 3).forEach((race, ri) => {
      console.log(`\n${indent}    === Race ${ri+1} ===`);
      const raceScalar = ['id','no','status','raceName_en','raceName_ch','postTime','distance','raceClass_en','raceClass_ch','ratingType'];
      raceScalar.forEach(f => {
        if (race[f] !== undefined) console.log(`${indent}      ${f}= ${race[f]}`);
      });
      
      if (race.runners && race.runners.length > 0) {
        console.log(`${indent}      runners [${race.runners.length} horses]:`);
        // Print first runner in detail
        const r = race.runners[0];
        console.log(`${indent}        runner[0] keys: ${Object.keys(r).join(', ')}`);
        // Draw, wt., etc.
        ['no','name_ch','name_en','draw','wt','horse','jockey','trainer','last6'].forEach(k => {
          if (r[k] !== undefined) {
            const v = typeof r[k] === 'object' ? JSON.stringify(r[k]).substring(0,80) : r[k];
            console.log(`${indent}        ${k}= ${v}`);
          }
        });
      }
    });
  }
  
  // pmPools
  if (meeting.pmPools && meeting.pmPools.length > 0) {
    console.log(`\n${indent}  pmPools [${meeting.pmPools.length}]:`);
    meeting.pmPools.slice(0,2).forEach((pool, pi) => {
      console.log(`${indent}    Pool ${pi}: oddsType=${pool.oddsType}, keys=${Object.keys(pool).join(', ')}`);
      if (pool.oddsNodes && pool.oddsNodes.length > 0) {
        console.log(`${indent}      oddsNodes[0]: ${JSON.stringify(pool.oddsNodes[0])}`);
      }
    });
  }
}

main().catch(e => { console.error(e); process.exit(1); });
