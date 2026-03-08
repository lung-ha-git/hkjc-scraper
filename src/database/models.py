"""
HKJC Racing Database Models
MongoDB connection and data models
"""

from pymongo import MongoClient
from datetime import datetime
from typing import Optional, List, Dict, Any


class Database:
    def __init__(self, connection_string: str = "mongodb://localhost:27017/"):
        self.client = MongoClient(connection_string)
        self.db = self.client["hkjc_racing"]
        
    @property
    def races(self):
        return self.db.races
    
    @property
    def horses(self):
        return self.db.horses
    
    @property
    def jockeys(self):
        return self.db.jockeys
    
    @property
    def trainers(self):
        return self.db.trainers
    
    @property
    def predictions(self):
        return self.db.predictions
    
    def create_indexes(self):
        """Create database indexes"""
        self.races.create_index("race_id", unique=True)
        self.races.create_index([("date", -1)])
        self.horses.create_index("horse_id", unique=True)
        self.horses.create_index("horse_name")
        self.jockeys.create_index("name", unique=True)
        self.trainers.create_index("name", unique=True)
        self.predictions.create_index([("race_id", 1), ("horse_id", 1)])
        print("Indexes created successfully")


class Race:
    """Race data model"""
    def __init__(self, data: Dict[str, Any]):
        self.race_id = data.get("race_id")
        self.date = data.get("date")
        self.venue = data.get("venue")  # HV or ST
        self.race_no = data.get("race_no")
        self.distance = data.get("distance")
        self.course = data.get("course")  # TURF, AWT
        self.track_condition = data.get("track_condition")
        self.race_class = data.get("race_class")
        self.total_runners = data.get("total_runners")
        self.runners = data.get("runners", [])
    
    def to_dict(self) -> Dict:
        return {
            "race_id": self.race_id,
            "date": self.date,
            "venue": self.venue,
            "race_no": self.race_no,
            "distance": self.distance,
            "course": self.course,
            "track_condition": self.track_condition,
            "race_class": self.race_class,
            "total_runners": self.total_runners,
            "runners": self.runners,
            "created_at": datetime.now()
        }


class Horse:
    """Horse data model"""
    def __init__(self, data: Dict[str, Any]):
        self.horse_id = data.get("horse_id")
        self.horse_name = data.get("horse_name")
        self.sex = data.get("sex")
        self.age = data.get("age")
        self.country = data.get("country")
        
    def to_dict(self) -> Dict:
        return {
            "horse_id": self.horse_id,
            "horse_name": self.horse_name,
            "sex": self.sex,
            "age": self.age,
            "country": self.country,
            "created_at": datetime.now()
        }


if __name__ == "__main__":
    db = Database()
    db.create_indexes()
    print("Database initialized!")
