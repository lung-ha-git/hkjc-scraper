/**
 * FEAT-007 7.3 — Extract racecard data from GraphQL raceMeetings operation ONLY
 *
 * Uses page.route to intercept and only process raceMeetings operation responses.
 */

const { chromium } = require('playwright');

const DATE = process.argv[2] || '2026-03-22';
const VENUE = process.argv[3] || 'ST';

async function main() {
  console.error(`\n🔍 GraphQL raceMeetings: ${DATE} ${VENUE}`);

  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();

  const racecards = [], entries = [];
  let responseData = null;

  // Intercept ALL graphql POST responses via route
  await page.route('**/graphql/**', async (route, request) => {
    const url = request.url();
    const method = request.method();
    if (method !== 'POST') {
      await route.continue();
      return;
    }

    const body = request.postData() || '';
    let isRaceMeetings = false;
    try {
      const parsed = JSON.parse(body);
      isRaceMeetings = parsed.operationName === 'raceMeetings';
    } catch (e) {}

    if (!isRaceMeetings) {
      // Not raceMeetings — let it through without interception
      await route.continue();
      return;
    }

    // It's a raceMeetings request — intercept the response
    const response = await route.fetch();
    const ct = response.headers()['content-type'] || '';
    let text = '';
    if (ct.includes('json')) {
      text = await response.text();
      try {
        const json = JSON.parse(text);
        const meetings = json?.data?.raceMeetings;
        if (meetings && meetings.length > 0) {
          const meeting = meetings[0];
          const races = meeting.races || [];
          races.forEach(race => {
            const raceNo = parseInt(race.no);
            racecards.push({
              race_no: raceNo,
              distance: race.distance || 0,
              class_en: race.raceClass_en || '',
              class_ch: race.raceClass_ch || '',
              race_name_en: race.raceName_en || '',
              race_name_ch: race.raceName_ch || '',
              post_time: race.postTime || '',
              rating_type: race.ratingType || '',
              race_track: race.raceTrack?.description_en || race.raceTrack?.description_ch || '',
              race_course: race.raceCourse?.displayCode || '',
              venue_code: meeting.venueCode || VENUE,
              meeting_date: meeting.date || DATE,
            });
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
                last6run: horse.last6run || '',
                horse_color: horse.color || '',
                horse_id: horse.horse?.code || '',
                horse_hkjc_id: horse.horse?.id || '',
                status: horse.status || 'Declared',
                final_position: horse.finalPosition || null,
                trump_card: horse.trumpCard || false,
                priority: horse.priority || false,
              });
            });
          });
        }
      } catch (e) {
        console.error('raceMeetings parse error:', e.message);
      }
    }

    // Reply with same response (no modification)
    await route.fulfill({
      status: response.status(),
      headers: response.headers(),
      contentType: ct,
      body: text,
    });
  });

  await page.goto(`https://bet.hkjc.com/ch/racing/wp/${DATE}/${VENUE}/1`, {
    waitUntil: 'domcontentloaded',
    timeout: 15000
  });

  await page.waitForTimeout(3000);
  await browser.close();

  console.error(`✅ Captured: ${racecards.length} races, ${entries.length} entries`);
  process.stdout.write('\n' + JSON.stringify({ racecards, entries }, null, 2) + '\n');
}

main().catch(e => { console.error(e); process.exit(1); });
