"""
SQLite Database Connection (Temporary for Testing)
Will migrate to MongoDB when available
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "hkjc.db"


class SQLiteConnection:
    """SQLite connection for testing"""
    
    def __init__(self, db_path: str = None):
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.conn: Optional[sqlite3.Connection] = None
        
    def connect(self) -> bool:
        """Connect to SQLite database"""
        try:
            self.conn = sqlite3.connect(str(self.db_path))
            self.conn.row_factory = sqlite3.Row
            return True
        except Exception as e:
            print(f"❌ SQLite connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close connection"""
        if self.conn:
            self.conn.close()
    
    def init_tables(self):
        """Initialize tables"""
        cursor = self.conn.cursor()
        
        # Races table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS races (
                race_id TEXT PRIMARY KEY,
                date TEXT,
                venue TEXT,
                race_no INTEGER,
                distance INTEGER,
                course TEXT,
                track_condition TEXT,
                race_class TEXT,
                runners TEXT,  -- JSON array
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Horses table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS horses (
                horse_id TEXT PRIMARY KEY,
                horse_name TEXT,
                sex TEXT,
                age INTEGER,
                country TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Raw results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                venue TEXT,
                race_no INTEGER,
                data TEXT,  -- JSON
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        print("✅ SQLite tables initialized")
    
    def insert_race(self, race_data: Dict[str, Any]):
        """Insert race data"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO races 
            (race_id, date, venue, race_no, distance, course, track_condition, race_class, runners)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            race_data.get('race_id'),
            race_data.get('date'),
            race_data.get('venue'),
            race_data.get('race_no'),
            race_data.get('distance'),
            race_data.get('course'),
            race_data.get('track_condition'),
            race_data.get('race_class'),
            json.dumps(race_data.get('runners', []))
        ))
        self.conn.commit()
    
    def insert_raw_result(self, date: str, venue: str, race_no: int, data: Dict):
        """Insert raw scraped result"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO raw_results (date, venue, race_no, data)
            VALUES (?, ?, ?, ?)
        ''', (date, venue, race_no, json.dumps(data)))
        self.conn.commit()
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM races")
        races_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM horses")
        horses_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM raw_results")
        raw_count = cursor.fetchone()[0]
        
        return {
            "races": races_count,
            "horses": horses_count,
            "raw_results": raw_count
        }


# For compatibility with MongoDB interface
db_connection = SQLiteConnection()


def get_db():
    """Get database connection"""
    if db_connection.conn is None:
        db_connection.connect()
        db_connection.init_tables()
    return db_connection
