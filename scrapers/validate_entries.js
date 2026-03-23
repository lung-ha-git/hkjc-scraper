/**
 * FEAT-006: Racecard vs Actual Entries Validation
 * Compare racecard_entries with odds page entries to detect changes
 */

const { chromium } = require('playwright');
const { MongoClient } = require('mongodb');

const MONGODB_URI = 'mongodb://localhost:27017/';
const DB_NAME = 'hkjc_racing_dev';

/**
 * Fetch actual entries from HKJC odds page GraphQL
 */
async function fetchOddsPageEntries(page, date, venue, raceNo) {
    return new Promise((resolve) => {
        const timeout = setTimeout(() => {
            page.removeListener('response', responseHandler);
            resolve(null);
        }, 10000);

        const responseHandler = async (response) => {
            const url = response.url();
            if (!url.includes('graphql') || !url.includes('info.cld.hkjc.com')) return;
            try {
                const body = await response.text();
                if (!body.includes('"runners"') || !body.includes('"pmPools"')) return;
                const json = JSON.parse(body);
                if (!json?.data?.raceMeetings?.[0]?.races?.[0]?.runners) return;
                
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
 * Parse runners from GraphQL response
 */
function parseRunners(data) {
    if (!data?.data?.raceMeetings?.[0]?.races?.[0]?.runners) return [];
    return data.data.raceMeetings[0].races[0].runners.map(r => {
        const isSubstitute = !!r.standbyNo && r.standbyNo !== '';
        return {
            horse_no: isSubstitute ? null : parseInt(r.no, 10),
            standby_no: r.standbyNo ? parseInt(r.standbyNo, 10) : null,
            status: r.status,
            name_ch: r.name_ch,
            name_en: r.name_en,
            draw: r.barrierDrawNumber ? parseInt(r.barrierDrawNumber, 10) : null,
            weight: r.handicapWeight ? parseInt(r.handicapWeight, 10) : null,
            jockey_code: r.jockey?.code || null,
            jockey_name: r.jockey?.name_ch || null,
            trainer_code: r.trainer?.code || null,
            trainer_name: r.trainer?.name_ch || null,
            last6run: r.last6run || null,
            is_substitute: isSubstitute
        };
    });
}

/**
 * Get racecard entries from MongoDB
 */
async function getRacecardEntries(db, date, venue, raceNo) {
    const entries = await db.collection('racecard_entries')
        .find({ race_date: date, venue, race_no: raceNo })
        .toArray();
    
    return entries.map(e => ({
        horse_no: e.horse_no,
        horse_name: e.horse_name,
        draw: e.draw,
        jockey_name: e.jockey_name,
        trainer_name: e.trainer_name,
        weight: e.weight_carried,
        horse_id: e.horse_id
    }));
}

/**
 * Compare two sets of entries and find differences
 */
function compareEntries(racecardEntries, oddsEntries) {
    const racecardMap = new Map(racecardEntries.map(e => [e.horse_no, e]));
    const oddsMap = new Map();
    const oddsByName = new Map();
    
    for (const e of oddsEntries) {
        if (e.horse_no !== null) {
            oddsMap.set(e.horse_no, e);
        }
        // Also index by name for matching substitutes
        const name = e.name_ch || e.name_en;
        if (name) {
            oddsByName.set(name, e);
        }
    }
    
    const added = [];      // In odds but not in racecard (by horse_no)
    const removed = [];    // In racecard but not in odds
    const substituted = []; // Has standby_no (substitute horses)
    const changed = [];    // Same horse_no but different details
    
    // Find added, changed, and substitutes
    for (const oddsEntry of oddsEntries) {
        // Skip substitutes from added/changed (they go in substituted)
        if (oddsEntry.is_substitute) {
            substituted.push({
                horse_no: oddsEntry.horse_no,
                standby_no: oddsEntry.standby_no,
                name: oddsEntry.name_ch || oddsEntry.name_en,
                status: oddsEntry.status
            });
            continue;
        }
        
        const racecardEntry = racecardMap.get(oddsEntry.horse_no);
        
        if (!racecardEntry) {
            added.push({
                horse_no: oddsEntry.horse_no,
                name: oddsEntry.name_ch || oddsEntry.name_en,
                odds_data: oddsEntry
            });
        } else {
            // Check for differences
            const differences = [];
            if (racecardEntry.draw !== oddsEntry.draw) {
                differences.push({ field: 'draw', racecard: racecardEntry.draw, odds: oddsEntry.draw });
            }
            if (racecardEntry.jockey_name !== oddsEntry.jockey_name) {
                differences.push({ field: 'jockey', racecard: racecardEntry.jockey_name, odds: oddsEntry.jockey_name });
            }
            if (racecardEntry.trainer_name !== oddsEntry.trainer_name) {
                differences.push({ field: 'trainer', racecard: racecardEntry.trainer_name, odds: oddsEntry.trainer_name });
            }
            if (racecardEntry.weight !== oddsEntry.weight) {
                differences.push({ field: 'weight', racecard: racecardEntry.weight, odds: oddsEntry.weight });
            }
            
            if (differences.length > 0) {
                changed.push({
                    horse_no: oddsEntry.horse_no,
                    name: oddsEntry.name_ch || oddsEntry.name_en,
                    differences
                });
            }
        }
    }
    
    // Find removed (only check non-null horse_no)
    for (const racecardEntry of racecardEntries) {
        if (!oddsMap.has(racecardEntry.horse_no)) {
            removed.push({
                horse_no: racecardEntry.horse_no,
                name: racecardEntry.horse_name,
                racecard_data: racecardEntry
            });
        }
    }
    
    return { added, removed, substituted, changed };
}

/**
 * Validate a single race
 */
async function validateRace(db, date, venue, raceNo, page = null) {
    const shouldCloseBrowser = !page;
    let browser;
    
    try {
        if (!page) {
            browser = await chromium.launch({ headless: true, channel: 'chrome' });
            page = await browser.newPage();
            await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
                waitUntil: 'domcontentloaded',
                timeout: 15000
            });
            await page.waitForTimeout(2000);
        }
        
        // Fetch odds page data
        const oddsData = await fetchOddsPageEntries(page, date, venue, raceNo);
        if (!oddsData) {
            return { error: 'Failed to fetch odds page data', race_no: raceNo };
        }
        
        const oddsEntries = parseRunners(oddsData);
        if (oddsEntries.length === 0) {
            return { error: 'No entries found on odds page', race_no: raceNo };
        }
        
        // Get racecard entries
        const racecardEntries = await getRacecardEntries(db, date, venue, raceNo);
        if (racecardEntries.length === 0) {
            return { error: 'No racecard entries found in database', race_no: raceNo };
        }
        
        // Compare
        const comparison = compareEntries(racecardEntries, oddsEntries);
        
        return {
            race_no: raceNo,
            racecard_count: racecardEntries.length,
            odds_count: oddsEntries.length,
            has_changes: comparison.added.length > 0 || 
                        comparison.removed.length > 0 || 
                        comparison.substituted.length > 0 ||
                        comparison.changed.length > 0,
            ...comparison
        };
        
    } finally {
        if (shouldCloseBrowser && browser) {
            await browser.close();
        }
    }
}

/**
 * Validate all races for a race day
 */
async function validateRaceDay(date, venue, races = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) {
    const client = new MongoClient(MONGODB_URI);
    
    try {
        await client.connect();
        const db = client.db(DB_NAME);
        
        console.log(`\n🔍 FEAT-006: Validating Racecard vs Odds Page Entries`);
        console.log(`📅 ${date} ${venue}`);
        console.log(`🏃 Races: ${races.join(', ')}\n`);
        
        const browser = await chromium.launch({ headless: true, channel: 'chrome' });
        const page = await browser.newPage();
        
        // Warm up
        await page.goto(`https://bet.hkjc.com/ch/racing/wp/${date}/${venue}/1`, {
            waitUntil: 'domcontentloaded',
            timeout: 15000
        });
        await page.waitForTimeout(2000);
        
        const results = [];
        
        for (const raceNo of races) {
            process.stdout.write(`  Race ${raceNo}... `);
            const result = await validateRace(db, date, venue, raceNo, page);
            results.push(result);
            
            if (result.error) {
                console.log(`⚠️  ${result.error}`);
            } else if (result.has_changes) {
                const changes = [];
                if (result.added?.length) changes.push(`+${result.added.length} added`);
                if (result.removed?.length) changes.push(`-${result.removed.length} removed`);
                if (result.substituted?.length) changes.push(`${result.substituted.length} substituted`);
                if (result.changed?.length) changes.push(`${result.changed.length} changed`);
                console.log(`🔄 ${changes.join(', ')}`);
            } else {
                console.log(`✅ No changes (${result.racecard_count} entries)`);
            }
        }
        
        await browser.close();
        
        // Save validation results to MongoDB
        const validationDoc = {
            date,
            venue,
            validated_at: new Date(),
            races: results,
            summary: {
                total_races: results.length,
                races_with_changes: results.filter(r => r.has_changes).length,
                total_added: results.reduce((sum, r) => sum + (r.added?.length || 0), 0),
                total_removed: results.reduce((sum, r) => sum + (r.removed?.length || 0), 0),
                total_substituted: results.reduce((sum, r) => sum + (r.substituted?.length || 0), 0),
                total_changed: results.reduce((sum, r) => sum + (r.changed?.length || 0), 0)
            }
        };
        
        await db.collection('racecard_validations').insertOne(validationDoc);
        
        // Print summary
        console.log(`\n📊 Validation Summary:`);
        console.log(`   Races checked: ${validationDoc.summary.total_races}`);
        console.log(`   Races with changes: ${validationDoc.summary.races_with_changes}`);
        console.log(`   Total added: ${validationDoc.summary.total_added}`);
        console.log(`   Total removed: ${validationDoc.summary.total_removed}`);
        console.log(`   Total substituted: ${validationDoc.summary.total_substituted}`);
        console.log(`   Total changed: ${validationDoc.summary.total_changed}`);
        
        // Print details for races with changes
        const changedRaces = results.filter(r => r.has_changes);
        if (changedRaces.length > 0) {
            console.log(`\n📝 Detailed Changes:`);
            for (const race of changedRaces) {
                console.log(`\n  Race ${race.race_no}:`);
                if (race.added?.length) {
                    console.log(`    Added:`);
                    race.added.forEach(h => console.log(`      #${h.horse_no}: ${h.name}`));
                }
                if (race.removed?.length) {
                    console.log(`    Removed:`);
                    race.removed.forEach(h => console.log(`      #${h.horse_no}: ${h.name}`));
                }
                if (race.substituted?.length) {
                    console.log(`    Substituted:`);
                    race.substituted.forEach(h => 
                        console.log(`      #${h.horse_no} (standby #${h.standby_no}): ${h.name}`)
                    );
                }
                if (race.changed?.length) {
                    console.log(`    Changed:`);
                    race.changed.forEach(h => {
                        console.log(`      #${h.horse_no}: ${h.name}`);
                        h.differences.forEach(d => 
                            console.log(`        ${d.field}: ${d.racecard} → ${d.odds}`)
                        );
                    });
                }
            }
        }
        
        console.log('\n✅ Validation complete. Results saved to racecard_validations collection.\n');
        return validationDoc;
        
    } finally {
        await client.close();
    }
}

// CLI
const args = process.argv.slice(2);
const date = args[0] || '2026-03-25';
const venue = args[1] || 'HV';
const racesArg = args.indexOf('--races');
const raceList = racesArg >= 0 
    ? args[racesArg + 1].split(',').map(Number)
    : undefined;

validateRaceDay(date, venue, raceList).catch(console.error);

module.exports = { validateRace, validateRaceDay, compareEntries, parseRunners };
