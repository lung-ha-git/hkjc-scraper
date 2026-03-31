#!/usr/bin/env python3
"""
Update incidents for existing races in the database.
Run this to scrape incidents for races that don't have them yet.
"""
import asyncio
import re
from playwright.async_api import async_playwright
from src.database.connection import DatabaseConnection
import sys


async def update_incidents():
    db = DatabaseConnection()
    db.connect()
    
    # Get all races
    races = list(db.db["races"].find({}, {
        "race_date": 1, 
        "race_no": 1, 
        "hkjc_race_id": 1,
        "venue": 1
    }))
    
    total = len(races)
    print(f"Total races to check: {total}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        for i, race in enumerate(races):
            race_date = race["race_date"]  # Format: 2024/03/06
            race_no = race["race_no"]
            hkjc_id = race["hkjc_race_id"]
            venue = race.get("venue", "ST")
            
            # Build URL
            url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={race_date}&Racecourse={venue}&RaceNo={race_no}"
            
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=20000)
                await asyncio.sleep(0.5)  # Small delay
            except Exception as e:
                await page.close()
                if (i + 1) % 100 == 0:
                    print(f"[{i+1}/{total}] Error loading {hkjc_id}")
                continue
            
            # Extract incidents
            incidents = []
            try:
                tables = await page.query_selector_all("table")
                for table in tables:
                    table_text = await table.inner_text()
                    if "競賽事件" in table_text or "事故報告" in table_text:
                        rows = await table.query_selector_all("tr")
                        for row in rows[1:]:  # Skip header
                            cells = await row.query_selector_all("td")
                            if len(cells) >= 3:
                                rank_raw = (await cells[0].inner_text()).strip()
                                horse_num_raw = (await cells[1].inner_text()).strip()
                                horse_name = (await cells[2].inner_text()).strip()
                                incident_report = (await cells[3].inner_text()).strip() if len(cells) > 3 else ""
                                
                                # Extract horse number
                                horse_match = re.search(r'(\d+)', horse_num_raw)
                                horse_number = int(horse_match.group(1)) if horse_match else None
                                
                                # Parse rank
                                rank = None
                                if rank_raw.isdigit():
                                    rank = int(rank_raw)
                                elif rank_raw.upper() == "WV":
                                    rank = None
                                elif "平頭馬" in rank_raw:
                                    match = re.match(r'^(\d+)', rank_raw)
                                    if match:
                                        rank = int(match.group(1))
                                else:
                                    rank = rank_raw
                                
                                incidents.append({
                                    "rank": rank,
                                    "horse_number": horse_number,
                                    "horse_name": horse_name,
                                    "incident_report": incident_report
                                })
            except Exception as e:
                pass
            
            await page.close()
            
            # Update if incidents found
            if incidents:
                db.db["races"].update_one(
                    {"hkjc_race_id": hkjc_id},
                    {"$set": {"incidents": incidents}}
                )
                print(f"[{i+1}/{total}] {hkjc_id}: {len(incidents)} incidents")
            elif (i + 1) % 100 == 0:
                print(f"[{i+1}/{total}] Checked...")
        
        await browser.close()
    
    print("Done!")


if __name__ == "__main__":
    asyncio.run(update_incidents())
