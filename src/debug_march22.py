#!/usr/bin/env python3
"""
Debug script to check March 22, 2026 fixture and racecard data
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.database.connection import DatabaseConnection

def check_march_22():
    db = DatabaseConnection()
    if not db.connect():
        print("Failed to connect to MongoDB")
        return
    
    # Check fixtures for March 22
    print("=" * 60)
    print("Checking fixtures collection for 2026-03-22")
    print("=" * 60)
    
    fixtures = list(db.db["fixtures"].find({"date": "2026-03-22"}))
    print(f"Found {len(fixtures)} fixture(s):")
    for f in fixtures:
        print(f"  - {f.get('date')} | venue: {f.get('venue')} | races: {f.get('race_count')} | status: {f.get('scrape_status')}")
    
    # Check racecards for March 22
    print("\n" + "=" * 60)
    print("Checking racecards collection for 2026-03-22")
    print("=" * 60)
    
    racecards_st = list(db.db["racecards"].find({"race_date": "2026-03-22", "venue": "ST"}))
    racecards_hv = list(db.db["racecards"].find({"race_date": "2026-03-22", "venue": "HV"}))
    
    print(f"ST racecards: {len(racecards_st)}")
    for rc in racecards_st[:3]:
        print(f"  - R{rc.get('race_no')}: {len(rc.get('horses', []))} horses")
    
    print(f"\nHV racecards: {len(racecards_hv)}")
    for rc in racecards_hv[:3]:
        print(f"  - R{rc.get('race_no')}: {len(rc.get('horses', []))} horses")
    
    # Check racecard_entries
    print("\n" + "=" * 60)
    print("Checking racecard_entries collection for 2026-03-22")
    print("=" * 60)
    
    entries_st = db.db["racecard_entries"].count_documents({"race_date": "2026-03-22", "venue": "ST"})
    entries_hv = db.db["racecard_entries"].count_documents({"race_date": "2026-03-22", "venue": "HV"})
    
    print(f"ST entries: {entries_st}")
    print(f"HV entries: {entries_hv}")
    
    db.disconnect()
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    if fixtures:
        expected_venue = fixtures[0].get('venue')
        print(f"Expected venue from fixture: {expected_venue}")
        
        if expected_venue == "HV":
            if len(racecards_hv) == 0 and len(racecards_st) > 0:
                print("BUG CONFIRMED: Fixture says HV but racecards were scraped as ST!")
            elif len(racecards_hv) > 0:
                print("OK: Racecards match fixture venue (HV)")
        elif expected_venue == "ST":
            if len(racecards_st) == 0 and len(racecards_hv) > 0:
                print("BUG CONFIRMED: Fixture says ST but racecards were scraped as HV!")
            elif len(racecards_st) > 0:
                print("OK: Racecards match fixture venue (ST)")

if __name__ == "__main__":
    check_march_22()
