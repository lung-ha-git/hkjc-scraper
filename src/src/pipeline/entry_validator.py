"""
FEAT-006: Racecard vs Actual Entries Validation
Compare racecard_entries with odds page entries to detect changes (substitutes, etc.)
"""

import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Optional, Any

import subprocess
import json

logger = logging.getLogger(__name__)


@dataclass
class EntryDiff:
    """Represents a difference in an entry"""
    field: str
    racecard_value: Any
    odds_value: Any


@dataclass
class ValidationResult:
    """Result of validating a single race"""
    race_no: int
    racecard_count: int
    odds_count: int
    has_changes: bool
    added: List[Dict]  # In odds but not racecard
    removed: List[Dict]  # In racecard but not odds
    substituted: List[Dict]  # Has standby_no
    changed: List[Dict]  # Same horse_no but different details
    error: Optional[str] = None


@dataclass
class ValidationSummary:
    """Summary of validating a race day"""
    date: str
    venue: str
    validated_at: datetime
    total_races: int
    races_with_changes: int
    total_added: int
    total_removed: int
    total_substituted: int
    total_changed: int


class EntryValidator:
    """Validates racecard entries against odds page entries"""
    
    def __init__(self, db):
        self.db = db
        
    async def validate_race(self, date: str, venue: str, race_no: int) -> ValidationResult:
        """
        Validate a single race by calling Node.js script
        """
        try:
            # Call Node.js script for single race validation
            cmd = [
                'node', '-e',
                f'''
const {{ validateRace }} = require('./scrapers/validate_entries.js');
const {{ MongoClient }} = require('mongodb');

async function run() {{
    const client = new MongoClient('mongodb://localhost:27017/');
    await client.connect();
    const db = client.db('hkjc_racing_dev');
    const result = await validateRace(db, '{date}', '{venue}', {race_no});
    await client.close();
    console.log(JSON.stringify(result));
}}
run().catch(e => {{ console.error(e); process.exit(1); }});
                '''
            ]
            
            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd='/Users/fatlung/.openclaw/workspace-main/hkjc_project'
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode != 0:
                logger.error(f"Validation failed for R{race_no}: {stderr.decode()}")
                return ValidationResult(
                    race_no=race_no,
                    racecard_count=0,
                    odds_count=0,
                    has_changes=False,
                    added=[], removed=[], substituted=[], changed=[],
                    error=stderr.decode()[:200]
                )
            
            data = json.loads(stdout.decode())
            return ValidationResult(
                race_no=data['race_no'],
                racecard_count=data.get('racecard_count', 0),
                odds_count=data.get('odds_count', 0),
                has_changes=data.get('has_changes', False),
                added=data.get('added', []),
                removed=data.get('removed', []),
                substituted=data.get('substituted', []),
                changed=data.get('changed', []),
                error=data.get('error')
            )
            
        except Exception as e:
            logger.error(f"Error validating R{race_no}: {e}")
            return ValidationResult(
                race_no=race_no,
                racecard_count=0,
                odds_count=0,
                has_changes=False,
                added=[], removed=[], substituted=[], changed=[],
                error=str(e)[:200]
            )
    
    async def validate_race_day(
        self, 
        date: str, 
        venue: str, 
        races: List[int] = None
    ) -> Dict:
        """
        Validate all races for a race day
        
        Returns validation document for MongoDB storage
        """
        if races is None:
            # Get race count from racecards
            race_count = self.db.db['racecards'].count_documents({
                'race_date': date,
                'venue': venue
            })
            races = list(range(1, max(race_count + 1, 11)))
        
        logger.info(f"FEAT-006: Validating {date} {venue} - {len(races)} races")
        
        # Run validations concurrently
        results = await asyncio.gather(*[
            self.validate_race(date, venue, race_no)
            for race_no in races
        ])
        
        # Build summary
        summary = ValidationSummary(
            date=date,
            venue=venue,
            validated_at=datetime.now(),
            total_races=len(results),
            races_with_changes=sum(1 for r in results if r.has_changes),
            total_added=sum(len(r.added) for r in results),
            total_removed=sum(len(r.removed) for r in results),
            total_substituted=sum(len(r.substituted) for r in results),
            total_changed=sum(len(r.changed) for r in results)
        )
        
        # Build validation document
        validation_doc = {
            'date': date,
            'venue': venue,
            'validated_at': datetime.now(),
            'races': [asdict(r) for r in results],
            'summary': {
                'total_races': summary.total_races,
                'races_with_changes': summary.races_with_changes,
                'total_added': summary.total_added,
                'total_removed': summary.total_removed,
                'total_substituted': summary.total_substituted,
                'total_changed': summary.total_changed
            }
        }
        
        # Save to MongoDB
        self.db.db['racecard_validations'].insert_one(validation_doc)
        
        # Log summary
        logger.info(f"Validation complete: {summary.races_with_changes}/{summary.total_races} races with changes")
        if summary.total_added:
            logger.info(f"  Added: {summary.total_added}")
        if summary.total_removed:
            logger.info(f"  Removed: {summary.total_removed}")
        if summary.total_substituted:
            logger.info(f"  Substituted: {summary.total_substituted}")
        if summary.total_changed:
            logger.info(f"  Changed: {summary.total_changed}")
        
        return validation_doc
    
    def get_latest_validation(self, date: str, venue: str) -> Optional[Dict]:
        """Get the most recent validation for a race day"""
        return self.db.db['racecard_validations'].find_one(
            {'date': date, 'venue': venue},
            sort=[('validated_at', -1)]
        )
    
    def has_entry_changes(self, date: str, venue: str, race_no: int) -> bool:
        """Check if a specific race has entry changes"""
        validation = self.get_latest_validation(date, venue)
        if not validation:
            return False
        
        for race in validation.get('races', []):
            if race['race_no'] == race_no:
                return race.get('has_changes', False)
        return False


async def run_validation(date: str, venue: str) -> Dict:
    """
    Standalone function to run validation
    """
    import sys
    sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')
    from src.database.connection import DatabaseConnection
    
    db = DatabaseConnection()
    if not db.connect():
        raise RuntimeError("Failed to connect to MongoDB")
    
    try:
        validator = EntryValidator(db)
        return await validator.validate_race_day(date, venue)
    finally:
        db.disconnect()


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)
    
    date = sys.argv[1] if len(sys.argv) > 1 else '2026-03-25'
    venue = sys.argv[2] if len(sys.argv) > 2 else 'HV'
    
    result = asyncio.run(run_validation(date, venue))
    print(json.dumps(result['summary'], indent=2, default=str))
