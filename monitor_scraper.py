#!/usr/bin/env python3
"""
Monitor scraper progress and send LINE notification when complete
"""

import time
import subprocess
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def check_scraper_done():
    """Check if scraper process is still running"""
    result = subprocess.run(
        ["ps", "aux"], 
        capture_output=True, 
        text=True
    )
    return "hkjc_complete_scraper.py" not in result.stdout

def get_stats():
    """Get current scraper stats"""
    from src.database.connection import DatabaseConnection
    db = DatabaseConnection()
    if not db.connect():
        return {}
    
    stats = {}
    for coll in ['horses', 'horse_race_history', 'horse_movements', 
                  'horse_distance_stats', 'horse_workouts', 'horse_medical',
                  'horse_pedigree', 'races']:
        stats[coll] = db.db[coll].count_documents({})
    
    db.disconnect()
    return stats

def send_line_message(message):
    """Send LINE message via OpenClaw message tool"""
    import json
    subprocess.run([
        "openclaw", "message", "send",
        "--channel", "line",
        "--message", message
    ], check=False)

def main():
    print("🔔 Starting scraper monitor...")
    
    while not check_scraper_done():
        stats = get_stats()
        print(f"⏳ Running... horses: {stats.get('horses', 0)}, races: {stats.get('races', 0)}")
        time.sleep(60)  # Check every minute
    
    # Scraper done - get final stats
    stats = get_stats()
    
    message = f"""🏇 HKJC Scraper 完成！

📊 數據統計:
- Horses: {stats.get('horses', 0)}
- Race History: {stats.get('horse_race_history', 0)}
- Movements: {stats.get('horse_movements', 0)}
- Distance Stats: {stats.get('horse_distance_stats', 0)}
- Workouts: {stats.get('horse_workouts', 0)}
- Medical: {stats.get('horse_medical', 0)}
- Pedigree: {stats.get('horse_pedigree', 0)}
- Races: {stats.get('races', 0)}"""
    
    print(message)
    
    # Try to send LINE message
    try:
        send_line_message(message)
        print("✅ LINE notification sent")
    except Exception as e:
        print(f"⚠️  LINE send failed: {e}")

if __name__ == "__main__":
    main()
