"""
Data Validation for HKJC Racing Data
"""

from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import re


class DataValidator:
    """Validate race data before processing"""
    
    # Valid values
    VALID_VENUES = ["HV", "ST"]  # Happy Valley, Sha Tin
    VALID_COURSES = ["TURF", "AWT", "AWC"]
    VALID_TRACK_CONDITIONS = ["GF", "G", "Y", "SC", "WF", "HY"]
    VALID_SEX_CODES = ["C", "H", "G", "M", "F"]
    
    # Distance range
    MIN_DISTANCE = 800
    MAX_DISTANCE = 2400
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate_race(self, race_data: Dict) -> Tuple[bool, List[str], List[str]]:
        """
        Validate race data
        
        Returns:
            (is_valid, errors, warnings)
        """
        self.errors = []
        self.warnings = []
        
        # Required fields
        required = ["race_id", "date", "venue", "race_no", "runners"]
        for field in required:
            if field not in race_data or not race_data[field]:
                self.errors.append(f"Missing required field: {field}")
        
        if self.errors:
            return False, self.errors, self.warnings
        
        # Validate date format
        if not self._validate_date(race_data.get("date")):
            self.errors.append(f"Invalid date format: {race_data.get('date')}")
        
        # Validate venue
        venue = race_data.get("venue")
        if venue and venue not in self.VALID_VENUES:
            self.errors.append(f"Invalid venue: {venue}. Must be one of {self.VALID_VENUES}")
        
        # Validate distance
        distance = race_data.get("distance")
        if distance:
            try:
                dist = int(distance)
                if not (self.MIN_DISTANCE <= dist <= self.MAX_DISTANCE):
                    self.warnings.append(f"Unusual distance: {dist}m (expected {self.MIN_DISTANCE}-{self.MAX_DISTANCE})")
            except:
                self.errors.append(f"Invalid distance: {distance}")
        
        # Validate track condition
        condition = race_data.get("track_condition")
        if condition and condition not in self.VALID_TRACK_CONDITIONS:
            self.warnings.append(f"Unusual track condition: {condition}")
        
        # Validate runners
        runners = race_data.get("runners", [])
        if not runners:
            self.errors.append("No runners in race")
        elif len(runners) > 14:
            self.warnings.append(f"Unusual number of runners: {len(runners)}")
        
        # Validate each runner
        for i, runner in enumerate(runners):
            self._validate_runner(runner, i)
        
        return len(self.errors) == 0, self.errors, self.warnings
    
    def _validate_date(self, date_str: str) -> bool:
        """Validate date is in correct format"""
        if not date_str:
            return False
        
        for fmt in ["%Y-%m-%d", "%d/%m/%Y"]:
            try:
                datetime.strptime(str(date_str), fmt)
                return True
            except:
                continue
        return False
    
    def _validate_runner(self, runner: Dict, index: int):
        """Validate a single runner's data"""
        prefix = f"Runner {index + 1}"
        
        # Check required fields
        if not runner.get("horse_name"):
            self.errors.append(f"{prefix}: Missing horse name")
        
        if not runner.get("jockey"):
            self.warnings.append(f"{prefix}: Missing jockey name")
        
        if not runner.get("trainer"):
            self.warnings.append(f"{prefix}: Missing trainer name")
        
        # Validate position
        position = runner.get("position")
        if position:
            try:
                pos = int(position)
                if pos < 1 or pos > 20:
                    self.warnings.append(f"{prefix}: Unusual position: {pos}")
            except:
                # Could be "DNF", "DQ", etc.
                if position not in ["DNF", "DQ", "WR", "UR"]:
                    self.warnings.append(f"{prefix}: Unknown position code: {position}")
    
    def validate_horse(self, horse_data: Dict) -> Tuple[bool, List[str], List[str]]:
        """Validate horse data"""
        self.errors = []
        self.warnings = []
        
        if not horse_data.get("horse_id"):
            self.errors.append("Missing horse_id")
        
        if not horse_data.get("horse_name"):
            self.errors.append("Missing horse_name")
        
        # Validate sex code
        sex = horse_data.get("sex")
        if sex and sex not in self.VALID_SEX_CODES:
            self.warnings.append(f"Unknown sex code: {sex}")
        
        # Validate age
        age = horse_data.get("age")
        if age:
            try:
                age_int = int(age)
                if age_int < 2 or age_int > 15:
                    self.warnings.append(f"Unusual age: {age_int}")
            except:
                self.errors.append(f"Invalid age: {age}")
        
        return len(self.errors) == 0, self.errors, self.warnings
    
    def validate_jockey(self, jockey_data: Dict) -> Tuple[bool, List[str], List[str]]:
        """Validate jockey data"""
        self.errors = []
        self.warnings = []
        
        if not jockey_data.get("name"):
            self.errors.append("Missing jockey name")
        
        # Validate win rate if present
        win_rate = jockey_data.get("win_rate")
        if win_rate is not None:
            try:
                rate = float(win_rate)
                if rate < 0 or rate > 1:
                    self.errors.append(f"Invalid win rate: {rate} (must be 0-1)")
            except:
                self.errors.append(f"Invalid win rate format: {win_rate}")
        
        return len(self.errors) == 0, self.errors, self.warnings


def sanitize_string(value: Any) -> str:
    """Clean and sanitize string input"""
    if not value:
        return ""
    
    # Convert to string
    text = str(value)
    
    # Remove extra whitespace
    text = " ".join(text.split())
    
    # Remove special characters that might cause issues
    text = re.sub(r'[<>\"\']', '', text)
    
    return text.strip()


def validate_numeric(value: Any, min_val: float = None, max_val: float = None) -> Optional[float]:
    """Validate and convert numeric value"""
    if value is None or value == "":
        return None
    
    try:
        num = float(value)
        
        if min_val is not None and num < min_val:
            return None
        if max_val is not None and num > max_val:
            return None
        
        return num
    except:
        return None


if __name__ == "__main__":
    # Test validation
    validator = DataValidator()
    
    test_race = {
        "race_id": "20260301_R1",
        "date": "2026-03-01",
        "venue": "HV",
        "race_no": 1,
        "distance": 1200,
        "runners": [
            {"horse_name": "Test Horse", "jockey": "Jockey A", "position": "1"},
            {"horse_name": "", "jockey": "", "position": "2"}  # Missing name
        ]
    }
    
    is_valid, errors, warnings = validator.validate_race(test_race)
    print(f"Valid: {is_valid}")
    print(f"Errors: {errors}")
    print(f"Warnings: {warnings}")
