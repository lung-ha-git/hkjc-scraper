/**
 * FEAT-007 7.3 — Prototype: Extract racecard data from GraphQL
 * 
 * Output matches racecards.py format:
 * { racecards: [{ race_no, distance, class, ... }],
 *   entries: [{ horse_no, horse_name, jockey_name, trainer_name, draw, ... }] }
 * 
 * Usage:
 *   node graphql_racecards.js [date] [venue]
 *   node graphql_racecards.js 2026-03-22 ST
 */

const { chromium } = require('playwright');

const DATE = process.argv[2] || '2026-03-22';
const VENUE = process.argv[3] || 'ST';

async function main() {
  console.error(`\n🔍 GraphQL Racecards: ${DATE} ${VENUE}`);

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();

  let racecards = [], entries = [];

  page.on('response', async (response) => {
    const url = response.url();
    if (!url.includes('graphql') && !url.includes('info.cld.hkjc.com')) return;
    
    try {
      const body = await response.text();
      if (!body || body.length < 1000) return; // Skip tiny responses
      
      let json;
      try { json = JSON.parse(body); } catch { return; }
      
      const meetings = json?.data?.raceMeetings;
      if (!meetings || meetings.length === 0) return;
      
      const meeting = meetings[0];
      const races = meeting.races || [];
      
      if (races.length === 0) return;
      
      // Extract racecard + entries
      races.forEach(race => {
        const raceNo = parseInt(race.no);
        
        // Race-level info
        racecards.push({
          race_no: raceNo,
          distance: race.distance || 0,
          class_en: race.raceClass_en || '',
          class_ch: race.raceClass_ch || '',
          race_name_en: race.raceName_en || '',
          race_name_ch: race.raceName_ch || '',
          post_time: race.postTime || '',
          rating_type: race.ratingType || '',
          race_track: race.raceTrack ? race.raceTrack.description_en || race.raceTrack.description_ch || '' : '',
          race_course: race.raceCourse ? race.raceCourse.displayCode || '' : '',
        });
        
        // Runner-level entries
        (race.runners || []).forEach(horse => {
          entries.push({
            race_no: raceNo,
            horse_no: parseInt(horse.no) || 0,
            horse_name: horse.name_ch || horse.name_en || '',
            jockey_name: horse.jockey?.name_ch || horse.jockey?.name_en || '',
            jockey_code: horse.jockey?.code || '',
            trainer_name: horse.trainer?.name_ch || horse.trainer?.name_en || '',
            trainer_code: horse.trainer?.code || '',
            draw: horse.barrierDrawNumber || null,
            weight_carried: horse.handicapWeight || null,
            rating: horse.currentRating || null,
            equipment: horse.gearInfo || '-',
            recent_form: horse.allowance || horse.last6run || '',
            last6run: horse.last6run || '',
            horse_color: horse.color || '',
            horse_id: horse.horse?.code || horse.horse?.id || '',
            horse_hkjc_id: horse.horse?.id || '',
            status: horse.status || 'Declared',
            final_position: horse.finalPosition || null,
            trump_card: horse.trumpCard || false,
            priority: horse.priority || false,
            allowance: horse.allowance || '',
          });
        });
      });
      
    } catch (e) {}
  });

  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${DATE}/${VENUE}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });

  await page.waitForTimeout(3000);
  await browser.close();

  const result = { racecards, entries };
  process.stdout.write('\n' + JSON.stringify(result, null, 2) + '\n');
}

main().catch(e => { console.error(e); process.exit(1); });
