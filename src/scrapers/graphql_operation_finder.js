/**
 * Find the exact GraphQL operation used for racecards
 */
const {chromium} = require('playwright');
const https = require('https');
const http = require('http');

async function main() {
  const browser = await chromium.launch({headless:true, channel:'chrome'});
  const page = await browser.newPage();
  
  // Intercept POST to graphql
  page.on('request', async req => {
    const u = req.url();
    if (!u.includes('graphql')) return;
    const method = req.method();
    if (method !== 'POST') return;
    const body = await req.postData();
    
    try {
      const parsed = JSON.parse(body);
      if (!parsed.query) return;
      const opName = parsed.operationName || parsed.query.match(/query (\w+)/)?.[1] || '';
      if (!opName) return;
      console.log(`\n=== POST /graphql ===`);
      console.log(`operationName: ${opName}`);
      console.log(`variables: ${JSON.stringify(parsed.variables)}`);
      console.log(`query: ${parsed.query.substring(0, 300)}`);
    } catch(e) {}
  });

  await page.goto('https://bet.hkjc.com/ch/racing/wp/2026-03-22/ST/1', {waitUntil:'domcontentloaded', timeout:15000});
  await page.waitForTimeout(3000);
  await browser.close();
}

main().catch(e => {console.error(e); process.exit(1)});
