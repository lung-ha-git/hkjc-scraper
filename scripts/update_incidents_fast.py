#!/usr/bin/env python3
"""
Fast update incidents using aiohttp instead of playwright.
"""
import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup
from src.database.connection import DatabaseConnection


async def fetch_and_parse(session, race_date, race_no, venue, hkjc_id, db):
    url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={race_date}&Racecourse={venue}&RaceNo={race_no}"
    
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                html = await resp.text()
                if "競賽事件" in html:
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find table with 競賽事件
                    tables = soup.find_all('table')
                    incidents = []
                    
                    for table in tables:
                        if "競賽事件" in table.get_text():
                            rows = table.find_all('tr')
                            for row in rows[1:]:  # Skip header
                                cells = row.find_all('td')
                                if len(cells) >= 3:
                                    rank_raw = cells[0].get_text().strip()
                                    horse_num_raw = cells[1].get_text().strip()
                                    horse_name = cells[2].get_text().strip()
                                    incident_report = cells[3].get_text().strip() if len(cells) > 3 else ""
                                    
                                    # Extract horse number
                                    horse_match = re.search(r'(\d+)', horse_num_raw)
                                    horse_number = int(horse_match.group(1)) if horse_match else None
                                    
                                    # Parse rank
                                    rank = None
                                    if rank_raw.isdigit():
                                        rank = int(rank_raw)
                                    elif rank_raw.upper() == "WV":
                                        rank = None
                                    else:
                                        rank = rank_raw
                                    
                                    incidents.append({
                                        "rank": rank,
                                        "horse_number": horse_number,
                                        "horse_name": horse_name,
                                        "incident_report": incident_report
                                    })
                    
                    if incidents:
                        db.db["races"].update_one(
                            {"hkjc_race_id": hkjc_id},
                            {"$set": {"incidents": incidents}}
                        )
                        print(f"✓ {hkjc_id}: {len(incidents)} incidents")
                        return len(incidents)
    except Exception as e:
        pass
    
    return 0


async def main():
    db = DatabaseConnection()
    db.connect()
    
    # Get races that might have incidents (check which ones have them)
    # Just check all races that don't have incidents yet
    races = list(db.db["races"].find(
        {"$or": [{"incidents": {"$exists": False}}, {"incidents": []}]},
        {"race_date": 1, "race_no": 1, "hkjc_race_id": 1, "venue": 1}
    ))
    
    print(f"Total races to check: {len(races)}")
    
    connector = aiohttp.TCPConnector(limit=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        batch = []
        for race in races:
            task = fetch_and_parse(
                session, 
                race["race_date"], 
                race["race_no"], 
                race.get("venue", "ST"),
                race["hkjc_race_id"],
                db
            )
            batch.append(task)
            
            # Process in batches
            if len(batch) >= 30:
                results = await asyncio.gather(*batch, return_exceptions=True)
                batch = []
                
                # Count successes
                count = sum(1 for r in results if isinstance(r, int) and r > 0)
                print(f"Batch done. Added: {count}")
        
        # Process remaining
        if batch:
            await asyncio.gather(*batch, return_exceptions=True)
    
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
