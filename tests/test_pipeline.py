"""
Unit tests for HKJC Racing Project
"""

import unittest
from src.etl.pipeline import ETLPipeline
from src.database.models import Database


class TestETLPipeline(unittest.TestCase):
    """Test ETL Pipeline"""
    
    def setUp(self):
        self.pipeline = ETLPipeline()
    
    def test_parse_date(self):
        """Test date parsing"""
        # Test different date formats
        self.assertEqual(
            self.pipeline._parse_date("2026-03-01"), 
            "2026-03-01"
        )
        self.assertEqual(
            self.pipeline._parse_date("01/03/2026"),
            "2026-03-01"
        )
    
    def test_parse_position(self):
        """Test position parsing"""
        self.assertEqual(self.pipeline._parse_position("1"), 1)
        self.assertEqual(self.pipeline._parse_position(""), 0)
        self.assertEqual(self.pipeline._parse_position("DNF"), 0)
    
    def test_process_race(self):
        """Test race data transformation"""
        sample_race = {
            "race_id": "20260301_R1",
            "date": "2026-03-01",
            "venue": "HV",
            "race_no": "1",
            "distance": "1200",
            "runners": [
                {"position": "1", "horse_no": "1", "horse_name": "Test Horse",
                 "jockey": "J", "trainer": "T", "time": "69.0", "margin": "0"}
            ]
        }
        
        result = self.pipeline.process_race(sample_race)
        
        self.assertEqual(result["race_id"], "20260301_R1")
        self.assertEqual(result["venue"], "HV")
        self.assertEqual(result["distance"], 1200)


class TestDatabase(unittest.TestCase):
    """Test Database Models"""
    
    def test_database_connection(self):
        """Test database can be instantiated"""
        db = Database("mongodb://localhost:27017/")
        self.assertIsNotNone(db.db)


if __name__ == "__main__":
    unittest.main()
