"""
Scraper Activity Log
Tracks progress, errors, and enables resume functionality
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class ScrapActivity:
    """Single scrap activity record"""
    timestamp: str
    phase: str  # horse_list, horse_detail, race_results
    horse_id: Optional[str] = None
    race_id: Optional[str] = None
    status: str = "started"  # started, completed, error, skipped
    records_count: int = 0
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class ScraperActivityLog:
    """Activity log for scraper workflow"""
    
    def __init__(self, log_file: str = None):
        if log_file is None:
            # Default to data/logs/activity.json
            base_dir = Path(__file__).resolve().parent.parent.parent
            log_dir = base_dir / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "scraper_activity.json"
        
        self.log_file = Path(log_file)
        self.activities: List[ScrapActivity] = []
        self._load()
    
    def _load(self):
        """Load existing activities from file"""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.activities = [ScrapActivity(**a) for a in data.get('activities', [])]
            except Exception as e:
                print(f"⚠️  Failed to load activity log: {e}")
                self.activities = []
    
    def _save(self):
        """Save activities to file"""
        data = {
            'last_updated': datetime.now().isoformat(),
            'total_activities': len(self.activities),
            'activities': [asdict(a) for a in self.activities]
        }
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def log_start(self, phase: str, horse_id: str = None, race_id: str = None):
        """Log start of an activity"""
        activity = ScrapActivity(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            horse_id=horse_id,
            race_id=race_id,
            status="started"
        )
        self.activities.append(activity)
        self._save()
        return activity
    
    def log_complete(self, phase: str, horse_id: str = None, race_id: str = None, 
                    records_count: int = 0, duration_ms: int = None):
        """Log completion of an activity"""
        activity = ScrapActivity(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            horse_id=horse_id,
            race_id=race_id,
            status="completed",
            records_count=records_count,
            duration_ms=duration_ms
        )
        self.activities.append(activity)
        self._save()
        return activity
    
    def log_error(self, phase: str, error: str, horse_id: str = None, race_id: str = None):
        """Log an error"""
        activity = ScrapActivity(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            horse_id=horse_id,
            race_id=race_id,
            status="error",
            error=error
        )
        self.activities.append(activity)
        self._save()
        return activity
    
    def log_skipped(self, phase: str, horse_id: str = None, race_id: str = None, reason: str = ""):
        """Log a skipped activity"""
        activity = ScrapActivity(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            horse_id=horse_id,
            race_id=race_id,
            status="skipped",
            error=reason
        )
        self.activities.append(activity)
        self._save()
        return activity
    
    def get_processed_horses(self, phase: str = None) -> set:
        """Get set of already processed horse IDs"""
        horses = set()
        for a in self.activities:
            if phase and a.phase != phase:
                continue
            if a.horse_id and a.status == "completed":
                horses.add(a.horse_id)
        return horses
    
    def get_processed_races(self) -> set:
        """Get set of already processed race IDs"""
        races = set()
        for a in self.activities:
            if a.race_id and a.status == "completed":
                races.add(a.race_id)
        return races
    
    def get_failed_horses(self) -> List[str]:
        """Get list of horse IDs that failed"""
        failed = []
        for a in self.activities:
            if a.horse_id and a.status == "error":
                failed.append(a.horse_id)
        return failed
    
    def get_last_activity(self, phase: str = None) -> Optional[ScrapActivity]:
        """Get last activity for a phase"""
        for a in reversed(self.activities):
            if phase and a.phase != phase:
                continue
            return a
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics"""
        stats = {
            "total": len(self.activities),
            "by_phase": {},
            "by_status": {},
            "completed_horses": 0,
            "completed_races": 0,
            "errors": 0
        }
        
        for a in self.activities:
            # By phase
            if a.phase not in stats["by_phase"]:
                stats["by_phase"][a.phase] = {"total": 0, "completed": 0, "error": 0}
            stats["by_phase"][a.phase]["total"] += 1
            if a.status == "completed":
                stats["by_phase"][a.phase]["completed"] += 1
            elif a.status == "error":
                stats["by_phase"][a.phase]["error"] += 1
            
            # By status
            if a.status not in stats["by_status"]:
                stats["by_status"][a.status] = 0
            stats["by_status"][a.status] += 1
            
            # Counts
            if a.horse_id and a.status == "completed":
                stats["completed_horses"] += 1
            if a.race_id and a.status == "completed":
                stats["completed_races"] += 1
            if a.status == "error":
                stats["errors"] += 1
        
        return stats
    
    def print_summary(self):
        """Print summary to console"""
        stats = self.get_stats()
        print("\n📊 Activity Log Summary")
        print("=" * 50)
        print(f"Total activities: {stats['total']}")
        print(f"Completed horses: {stats['completed_horses']}")
        print(f"Completed races: {stats['completed_races']}")
        print(f"Errors: {stats['errors']}")
        print("\nBy Phase:")
        for phase, data in stats["by_phase"].items():
            print(f"  {phase}: {data['completed']}/{data['total']} completed, {data['error']} errors")
    
    def clear(self):
        """Clear all activities"""
        self.activities = []
        self._save()
        print("🗑️  Activity log cleared")


# Singleton instance
_activity_log: Optional[ScraperActivityLog] = None

def get_activity_log(log_file: str = None) -> ScraperActivityLog:
    """Get or create the activity log singleton"""
    global _activity_log
    if _activity_log is None:
        _activity_log = ScraperActivityLog(log_file)
    return _activity_log
