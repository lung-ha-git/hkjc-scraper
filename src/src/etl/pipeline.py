"""
ETL Pipeline for HKJC Racing Data
Data extraction, transformation and loading
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from src.database.models import Database
from src.utils.validators import DataValidator, sanitize_string, validate_numeric
from src.utils import logger


class ETLPipeline:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.validator = DataValidator()
    
    def process_race(self, race_data: Dict) -> Optional[Dict]:
        """
        Transform raw race data to standard format
        
        Returns:
            Transformed data or None if validation fails
        """
        # Validate first
        is_valid, errors, warnings = self.validator.validate_race(race_data)
        
        if not is_valid:
            logger.error(f"Race validation failed: {errors}")
            return None
        
        if warnings:
            logger.warning(f"Race validation warnings: {warnings}")
        
        # Sanitize and transform
        transformed = {
            "race_id": sanitize_string(race_data.get("race_id")),
            "date": self._parse_date(race_data.get("date")),
            "venue": sanitize_string(race_data.get("venue")),
            "race_no": validate_numeric(race_data.get("race_no"), min_val=1, max_val=12) or 0,
            "distance": validate_numeric(race_data.get("distance"), min_val=800, max_val=2400) or 0,
            "course": sanitize_string(race_data.get("course", "TURF")),
            "track_condition": sanitize_string(race_data.get("track_condition", "GF")),
            "race_class": sanitize_string(race_data.get("race_class", "")),
            "total_runners": len(race_data.get("runners", [])),
            "runners": self._process_runners(race_data.get("runners", [])),
            "processed_at": datetime.now(),
            "validation_status": "passed",
            "validation_warnings": warnings
        }
        logger.info(f"Successfully processed race {transformed['race_id']}")
        return transformed
    
    def _parse_date(self, date_str: str) -> str:
        """Convert date string to standard format"""
        if not date_str:
            return ""
        
        # Try different formats
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"]:
            try:
                dt = datetime.strptime(str(date_str), fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str
    
    def _process_runners(self, runners: List[Dict]) -> List[Dict]:
        """Transform runner data"""
        processed = []
        for runner in runners:
            processed.append({
                "horse_no": runner.get("horse_no", ""),
                "horse_name": runner.get("horse_name", ""),
                "jockey": runner.get("jockey", ""),
                "trainer": runner.get("trainer", ""),
                "position": self._parse_position(runner.get("position", "")),
                "finish_time": runner.get("time", ""),
                "margin": runner.get("margin", "")
            })
        return processed
    
    def _parse_position(self, pos: str) -> int:
        """Convert position to integer"""
        try:
            return int(pos) if pos else 0
        except (ValueError, TypeError):
            return 0
    
    def load_races(self, races: List[Dict]) -> int:
        """Load races to MongoDB"""
        count = 0
        failed = 0
        
        for race in races:
            transformed = self.process_race(race)
            if not transformed:
                failed += 1
                continue
                
            try:
                self.db.races.update_one(
                    {"race_id": transformed["race_id"]},
                    {"$set": transformed},
                    upsert=True
                )
                count += 1
                logger.debug(f"Loaded race {transformed['race_id']}")
            except Exception as e:
                logger.error(f"Error loading race {transformed.get('race_id')}: {e}")
                failed += 1
        
        logger.info(f"Load complete: {count} succeeded, {failed} failed")
        return count
    
    def run(self, raw_data: List[Dict]) -> Dict:
        """Run full ETL pipeline"""
        logger.info(f"ETL Pipeline started: processing {len(raw_data)} races")
        
        # Transform
        transformed_races = [self.process_race(r) for r in raw_data]
        
        # Load
        loaded = self.load_races(transformed_races)
        
        return {
            "total": len(raw_data),
            "transformed": len(transformed_races),
            "loaded": loaded,
            "timestamp": datetime.now().isoformat()
        }


if __name__ == "__main__":
    # Test with sample data
    pipeline = ETLPipeline()
    
    sample_race = {
        "race_id": "20260301_R1",
        "date": "2026-03-01",
        "venue": "HV",
        "race_no": "1",
        "distance": "1200",
        "course": "TURF",
        "track_condition": "GF",
        "runners": [
            {"position": "1", "horse_no": "1", "horse_name": "電光速度", 
             "jockey": "潘頓", "trainer": "蔡約翰", "time": "69.35", "margin": "0"},
            {"position": "2", "horse_no": "2", "horse_name": "金星", 
             "jockey": "莫雷拉", "trainer": "沈集成", "time": "69.58", "margin": "1-1/4"}
        ]
    }
    
    result = pipeline.run([sample_race])
    print(f"ETL Result: {result}")
