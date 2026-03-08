"""
Mock HKJC Data Generator
Generate test race data for development and testing
"""

import random
from datetime import datetime, timedelta
from typing import List, Dict
import json


class MockHKJCGenerator:
    """Generate mock HKJC race data"""
    
    HORSE_NAMES = [
        "Golden Star", "Lucky Strike", "Thunder Bolt", "Silver Arrow",
        "Red Phoenix", "Dragon Fire", "Wind Runner", "Ocean Wave",
        "Mountain King", "Desert Storm", "Ice Crystal", "Flame Heart",
        "Moon Shadow", "Sun Dancer", "Night Rider", "Day Breaker",
        "Lightning Fast", "Storm Chaser", "Rainbow Dash", "Cloud Runner"
    ]
    
    JOCKEY_NAMES = [
        "Karis Teetan", "Zac Purton", "Joao Moreira", "Alexis Badel",
        "Matthew Poon", "Vincent Ho", "Keith Yeung", "Derek Leung",
        "Alfred Chan", "Luke Currie", "Blake Shinn", "Brett Prebble"
    ]
    
    TRAINER_NAMES = [
        "John Size", "Francis Lui", "Caspar Fownes", "Tony Cruz",
        "Danny Shum", "Ricky Yiu", "Jimmy Ting", "Jamie Richards",
        "Benno Yung", "Manfred Man", "Pierre Ng", "David Hayes"
    ]
    
    VENUES = ["HV", "ST"]  # Happy Valley, Sha Tin
    DISTANCES = [1000, 1200, 1400, 1600, 1800, 2000]
    
    def generate_race(self, date: str, venue: str, race_no: int) -> Dict:
        """Generate a single race with runners"""
        num_runners = random.randint(8, 14)
        
        runners = []
        for i in range(1, num_runners + 1):
            # Random finish time around 1:10 - 1:30 for most distances
            base_seconds = random.randint(70, 90)
            finish_time = f"1:{base_seconds:02d}.{random.randint(0, 99):02d}"
            
            runner = {
                "position": str(i) if i > 1 else "1",
                "horse_no": str(i),
                "horse_name": random.choice(self.HORSE_NAMES),
                "jockey": random.choice(self.JOCKEY_NAMES),
                "trainer": random.choice(self.TRAINER_NAMES),
                "finish_time": finish_time,
                "margin": "N" if i == 1 else f"+{random.uniform(0.5, 5.0):.1f}",
                "weight": str(random.randint(108, 133)),
                "draw": str(random.randint(1, 14))
            }
            runners.append(runner)
        
        return {
            "race_id": f"{date.replace('-', '')}_R{race_no}",
            "date": date,
            "venue": venue,
            "race_no": race_no,
            "distance": random.choice(self.DISTANCES),
            "course": random.choice(["TURF", "AWT"]),
            "track_condition": random.choice(["GF", "G", "Y", "SC"]),
            "race_class": f"Class {random.randint(1, 5)}",
            "total_runners": num_runners,
            "runners": runners,
            "scraped_at": datetime.now().isoformat()
        }
    
    def generate_race_day(self, date: str, venue: str = None) -> List[Dict]:
        """Generate a full race day (8-11 races)"""
        if venue is None:
            venue = random.choice(self.VENUES)
        
        # Race days typically have 8-11 races
        num_races = random.randint(8, 11)
        races = []
        
        for race_no in range(1, num_races + 1):
            race = self.generate_race(date, venue, race_no)
            races.append(race)
        
        return races
    
    def generate_multiple_days(self, days: int = 7) -> List[Dict]:
        """Generate data for multiple race days"""
        all_races = []
        today = datetime.now()
        
        for i in range(days):
            date = today - timedelta(days=i)
            # Only generate for Wednesdays (2) and Sundays (6)
            if date.weekday() in [2, 6]:
                date_str = date.strftime("%Y-%m-%d")
                races = self.generate_race_day(date_str)
                all_races.extend(races)
        
        return all_races


def generate_test_data() -> List[Dict]:
    """Generate test data for today"""
    generator = MockHKJCGenerator()
    today = datetime.now().strftime("%Y-%m-%d")
    return generator.generate_race_day(today, "ST")


if __name__ == "__main__":
    # Test
    generator = MockHKJCGenerator()
    races = generator.generate_race_day("2025-12-28", "ST")
    
    print(f"Generated {len(races)} races")
    for race in races[:2]:
        print(f"\nRace {race['race_no']}: {race['distance']}m, {race['track_condition']}")
        print(f"  Runners: {len(race['runners'])}")
        for runner in race['runners'][:3]:
            print(f"    {runner['position']}. {runner['horse_name']} ({runner['jockey']})")
