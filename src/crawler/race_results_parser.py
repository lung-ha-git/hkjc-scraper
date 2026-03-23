"""
HKJC Race Results Scraper - Using web_fetch approach
Parse race results from fetched HTML content
"""

import re
import asyncio
from datetime import datetime
from typing import Dict, List
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.database.connection import DatabaseConnection
from src.constants.payout_map import normalize_payout_keys


class RaceResultsParser:
    """Parse race results from HKJC page content"""
    
    def __init__(self):
        pass
    
    def parse_race_data(self, html_content: str, race_date: str, racecourse: str, race_no: int) -> Dict:
        """Parse race data from raw HTML/text content"""
        
        # Clean content
        text = html_content.strip()
        
        print(f"\n🏇 Parsing race: {race_date} {racecourse} Race {race_no}")
        
        # Extract metadata
        metadata = self._parse_metadata(text, race_date, racecourse, race_no)
        
        # Extract results
        results = self._parse_results(text)
        
        # Extract payouts
        payouts = self._parse_payouts(text)
        
        # Extract incidents
        incidents = self._parse_incidents(text)
        
        return {
            "race_date": race_date,
            "racecourse": racecourse,
            "race_no": race_no,
            "race_id": metadata.get("race_id"),
            "metadata": metadata,
            "results": results,
            "payout": payouts,  # normalized to English keys
            "incidents": incidents,
            "scraped_at": datetime.now().isoformat()
        }
    
    def _parse_metadata(self, text: str, race_date: str, racecourse: str, race_no: int) -> Dict:
        """Parse race metadata"""
        meta = {
            "race_date": race_date,
            "racecourse": racecourse,
            "race_no": race_no,
            "venue": "沙田" if racecourse == "ST" else "跑馬地",
        }
        
        # Race ID: 第 7 場 (481)
        race_id_match = re.search(r'第\s*(\d+)\s*場\s*\((\d+)\)', text)
        if race_id_match:
            meta["race_id"] = int(race_id_match.group(2))
        
        # Race name and distance: 一級賽 - 2000米
        race_match = re.search(r'([一二三]級賽|[一二三四五]班)\s*-\s*(\d+)米', text)
        if race_match:
            meta["class"] = race_match.group(1)
            meta["distance"] = int(race_match.group(2))
        
        # Race name: 花旗銀行香港金盃
        name_match = re.search(r'([^\n]+盃|[^\n]+賽)\s*[\n\r]', text)
        if name_match:
            meta["race_name"] = name_match.group(1).strip()
        
        # Prize: HK$ 13,000,000
        prize_match = re.search(r'HK\$\s*([\d,]+)', text)
        if prize_match:
            meta["prize"] = f"HK${prize_match.group(1)}"
        
        # Track: 草地 - "B+2" 賽道
        track_match = re.search(r'(草地|全天候跑道)\s*-\s*"([^"]+)"\s*賽道', text)
        if track_match:
            meta["course"] = track_match.group(1)
            meta["track"] = track_match.group(2)
        
        # Track condition: 場地狀況 : 好地
        condition_match = re.search(r'場地狀況\s*:\s*(\S+)', text)
        if condition_match:
            meta["track_condition"] = condition_match.group(1)
        
        # Sectional times
        sectional_times = re.findall(r'\((\d+\.?\d*)\)', text)
        if sectional_times:
            meta["sectional_times"] = sectional_times
        
        return meta
    
    def _parse_results(self, text: str) -> List[Dict]:
        """Parse race results table"""
        results = []
        
        # Find the results section
        # Pattern: position, horse_no, horse_name, jockey, trainer, weight, draw, distance, time, odds
        # The data is in lines like:
        # 1  1  [浪漫勇士](/zh-hk/... 麥道朗 沈集成  126  1166  4  -  1:59.77  1
        
        # Split by positions (lines starting with number)
        lines = text.split('\n')
        
        current_pos = None
        result = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this is a position line
            pos_match = re.match(r'^(\d+)\s+$', line)
            if pos_match:
                # Save previous result if exists
                if result and current_pos:
                    results.append(result)
                
                current_pos = int(pos_match.group(1))
                result = {"position": current_pos}
                continue
            
            # Extract horse number
            horse_no_match = re.match(r'^(\d+)\s+\[([^\]]+)\]', line)
            if horse_no_match and current_pos:
                result["horse_no"] = int(horse_no_match.group(1))
                # Horse link: /zh-hk/local/information/horse?horseid=HK_2020_E486
                horse_id_match = re.search(r'horseid=([^&\s]+)', line)
                if horse_id_match:
                    result["horse_id"] = horse_id_match.group(1)
                
                # Extract horse name (between ] and ()
                name_match = re.search(r'\]([^(]+)\(', line)
                if name_match:
                    result["horse_name"] = name_match.group(1).strip()
                
                # Extract other fields after the horse info
                # Fields: jockey, trainer, weight, draw, distance, time, odds
                parts = re.split(r'\s+', line)
                # This is complex - let's use a simpler approach
        
        # Alternative: Use regex to extract all results at once
        # Pattern for each horse entry
        pattern = r'(\d+)\s+(\d+)\s+\[([^\]]+)\]\s*\(([^)]+)\)\s*\[([^\]]+)\]\s*\(([^)]+)\)\s*\[([^\]]+)\]\s*\(([^)]+)\)\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+([\d.]+)\s+([\d.]+)'
        
        matches = re.findall(pattern, text)
        
        # Actually let's try a simpler text-based parse
        # The table structure is clear from the web_fetch output
        
        return results
    
    def _parse_results_v2(self, text: str) -> List[Dict]:
        """Parse results using simpler approach - look for blocks"""
        results = []
        
        # Split text into sections
        sections = text.split('名次')
        
        if len(sections) > 1:
            results_section = sections[1]
            
            # Find each horse block - starts with position number
            # Pattern: number at start of line
            lines = results_section.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if starts with a number (position)
                if re.match(r'^\d+\s+\d+', line):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pos = int(parts[0])
                            horse_no = int(parts[1])
                            
                            result = {
                                "position": pos,
                                "horse_no": horse_no
                            }
                            
                            # Extract horse ID from link
                            horse_id_match = re.search(r'horseid=([^&\s]+)', line)
                            if horse_id_match:
                                result["horse_id"] = horse_id_match.group(1)
                            
                            # Extract horse name
                            name_match = re.search(r'\[([^\]]+)\]', line)
                            if name_match:
                                result["horse_name"] = name_match.group(1)
                            
                            results.append(result)
                        except Exception:
                            pass
        
        return results
    
    def _parse_payouts(self, text: str) -> Dict:
        """Parse payouts table"""
        payouts = {}
        
        # Find section after "派彩"
        sections = text.split('派彩')
        
        if len(sections) > 1:
            payout_section = sections[1].split('競賽事件報告')[0]
            
            # Parse each pool
            # Pattern: PoolName  Combination  Amount
            lines = payout_section.split('\n')
            
            current_pool = None
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this is a pool name (no numbers at start)
                if not re.match(r'^\d', line) and line not in ['勝出組合', '派彩 (HK$)']:
                    current_pool = line
                    payouts[current_pool] = {}
                elif current_pool and re.match(r'^\d', line):
                    # This is a payout line
                    parts = line.split()
                    if len(parts) >= 2:
                        combo = parts[0]
                        amount = parts[1] if len(parts) > 1 else ""
                        payouts[current_pool][combo] = amount
        
        return normalize_payout_keys(payouts)
    
    def _parse_incidents(self, text: str) -> List[Dict]:
        """Parse incident reports"""
        incidents = []
        
        # Find section after "競賽事件報告"
        sections = text.split('競賽事件報告')
        
        if len(sections) > 1:
            incident_section = sections[1].split('勝出馬匹血統')[0]
            
            lines = incident_section.split('\n')
            
            current_incident = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check if this is a position line
                pos_match = re.match(r'^(\d+)\s+(\d+)\s+\[([^\]]+)\]', line)
                if pos_match:
                    if current_incident:
                        incidents.append(current_incident)
                    
                    current_incident = {
                        "position": int(pos_match.group(1)),
                        "horse_no": int(pos_match.group(2))
                    }
                    
                    # Horse ID
                    horse_id_match = re.search(r'horseid=([^&\s]+)', line)
                    if horse_id_match:
                        current_incident["horse_id"] = horse_id_match.group(1)
                    
                    # Horse name
                    name_match = re.search(r'\]([^(]+)\(', line)
                    if name_match:
                        current_incident["horse_name"] = name_match.group(1).strip()
                else:
                    # This is the report text
                    if current_incident and 'report' not in current_incident:
                        current_incident["report"] = line
            
            # Add last one
            if current_incident:
                incidents.append(current_incident)
        
        return incidents
    
    async def save_to_mongodb(self, race_data: Dict):
        """Save race data to MongoDB"""
        print("\n💾 Saving to MongoDB...")
        
        db = DatabaseConnection()
        if not db.connect():
            print("   ❌ Cannot connect to MongoDB")
            return
        
        race_id = f"{race_data['race_date']}_{race_data['racecourse']}_{race_data['race_no']}"
        
        # 1. Save race metadata
        race_doc = {
            "_id": race_id,
            **race_data["metadata"],
            "results_count": len(race_data["results"]),
            "scraped_at": race_data["scraped_at"]
        }
        db.db["races"].replace_one({"_id": race_id}, race_doc, upsert=True)
        print(f"   ✅ races: {race_id}")
        
        # 2. Save race results
        db.db["race_results"].delete_many({"race_id": race_id})
        for result in race_data["results"]:
            result["race_id"] = race_id
        if race_data["results"]:
            db.db["race_results"].insert_many(race_data["results"])
        print(f"   ✅ race_results: {len(race_data['results'])} records")
        
        # 3. Save payouts
        db.db["race_payouts"].replace_one(
            {"race_id": race_id},
            {"race_id": race_id, "pools": race_data["payout"], "scraped_at": race_data["scraped_at"]},
            upsert=True
        )
        print(f"   ✅ race_payouts: {len(race_data['payout'])} pools")
        
        # 4. Save incidents
        db.db["race_incidents"].delete_many({"race_id": race_id})
        for incident in race_data["incidents"]:
            incident["race_id"] = race_id
        if race_data["incidents"]:
            db.db["race_incidents"].insert_many(race_data["incidents"])
        print(f"   ✅ race_incidents: {len(race_data['incidents'])} records")
        
        db.disconnect()
        print("\n✅ All race data saved!")


async def main():
    """Test with race 2026/03/01 ST Race 7"""
    from web_fetch import web_fetch_tool
    
    parser = RaceResultsParser()
    
    # Fetch the page
    print("Fetching race page...")
    result = await web_fetch_tool({
        "url": "https://racing.hkjc.com/zh-hk/local/information/localresults?racedate=2026/03/01&Racecourse=ST&RaceNo=7",
        "maxChars": 50000
    })
    
    # Parse the content
    html_content = result.get("text", "")
    
    race_data = parser.parse_race_data(html_content, "2026/03/01", "ST", 7)
    
    print("\n" + "=" * 80)
    print("📊 PARSED RACE DATA")
    print("=" * 80)
    
    print(f"\n🏇 Race: {race_data['metadata'].get('race_name', 'N/A')}")
    print(f"   Distance: {race_data['metadata'].get('distance', 'N/A')}m")
    print(f"   Class: {race_data['metadata'].get('class', 'N/A')}")
    print(f"   Track: {race_data['metadata'].get('track', 'N/A')}")
    print(f"   Prize: {race_data['metadata'].get('prize', 'N/A')}")
    
    print(f"\n📋 Results: {len(race_data['results'])} horses")
    for r in race_data['results'][:5]:
        print(f"   {r}")
    
    print(f"\n💰 Payouts: {len(race_data['payouts'])} pools")
    
    print(f"\n📝 Incidents: {len(race_data['incidents'])} reports")
    
    # Save to MongoDB
    # await parser.save_to_mongodb(race_data)


if __name__ == "__main__":
    asyncio.run(main())
