"""
HKJC Data Pipeline - Main Runner
Daily automated data sync and model training pipeline
"""

import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys
import logging

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.pipeline.fixtures import sync_fixtures
from src.pipeline.racecards import scrape_next_racecards
from src.pipeline.history import sync_past_race_results
from src.pipeline.deep_sync import deep_sync_horse_data
from src.database.connection import DatabaseConnection

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineRunner:
    """Main pipeline orchestrator"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.db = DatabaseConnection()
        self.results = {
            "fixtures": 0,
            "racecards": 0,
            "race_results": 0,
            "deep_sync": 0,
            "errors": []
        }
    
    def run(self, pipeline: str = "all"):
        """Run specified pipeline(s)"""
        logger.info(f"🚀 Starting Pipeline: {pipeline} (dry_run={self.dry_run})")
        
        if pipeline == "all":
            self.run_full_pipeline()
        elif pipeline == "future":
            self.run_future_pipeline()
        elif pipeline == "history":
            self.run_history_pipeline()
        elif pipeline == "fixtures":
            self.run_fixtures()
        elif pipeline == "racecards":
            self.run_racecards()
        elif pipeline == "deep-sync":
            self.run_deep_sync()
        else:
            logger.error(f"Unknown pipeline: {pipeline}")
            return False
        
        self.log_summary()
        return len(self.results["errors"]) == 0
    
    def run_full_pipeline(self):
        """Run complete pipeline: fixtures -> racecards -> history -> deep-sync"""
        logger.info("=" * 60)
        logger.info("📋 FULL PIPELINE")
        logger.info("=" * 60)
        
        # Part 1: Sync fixtures
        self.run_fixtures()
        
        # Part 2: Scrape next race day racecards
        self.run_racecards()
        
        # Part 3: Sync past race results
        self.run_history()
        
        # Part 4: Deep sync horse data
        self.run_deep_sync()
    
    def run_future_pipeline(self):
        """Future Prediction Pipeline"""
        logger.info("=" * 60)
        logger.info("🔮 FUTURE PREDICTION PIPELINE")
        logger.info("=" * 60)
        
        self.run_fixtures()
        self.run_racecards()
    
    def run_history_pipeline(self):
        """Historical Optimization Pipeline"""
        logger.info("=" * 60)
        logger.info("📊 HISTORICAL OPTIMIZATION PIPELINE")
        logger.info("=" * 60)
        
        self.run_history()
        self.run_deep_sync()
    
    def run_fixtures(self):
        """Sync race fixtures/calendar"""
        logger.info("\n📅 Step 1: Syncing Fixtures...")
        
        if self.dry_run:
            logger.info("   [DRY RUN] Would sync fixtures")
            self.results["fixtures"] = 0
            return
        
        try:
            count = asyncio.run(sync_fixtures())
            self.results["fixtures"] = count
            logger.info(f"   ✅ Synced {count} fixtures")
        except Exception as e:
            logger.error(f"   ❌ Fixtures failed: {e}")
            self.results["errors"].append(f"fixtures: {e}")
    
    def run_racecards(self):
        """Scrape next race day racecards"""
        logger.info("\n🏇 Step 2: Scraping Next Race Day...")
        
        if self.dry_run:
            logger.info("   [DRY RUN] Would scrape racecards")
            self.results["racecards"] = 0
            return
        
        try:
            count = asyncio.run(scrape_next_racecards())
            self.results["racecards"] = count
            logger.info(f"   ✅ Scraped {count} races")
        except Exception as e:
            logger.error(f"   ❌ Racecards failed: {e}")
            self.results["errors"].append(f"racecards: {e}")
    
    def run_history(self):
        """Sync past race results"""
        logger.info("\n📜 Step 3: Syncing Past Race Results...")
        
        if self.dry_run:
            logger.info("   [DRY RUN] Would sync history")
            self.results["race_results"] = 0
            return
        
        try:
            count = asyncio.run(sync_past_race_results())
            self.results["race_results"] = count
            logger.info(f"   ✅ Synced {count} race results")
        except Exception as e:
            logger.error(f"   ❌ History sync failed: {e}")
            self.results["errors"].append(f"history: {e}")
    
    def run_deep_sync(self):
        """Deep sync horse data"""
        logger.info("\n🔄 Step 4: Deep Sync Horse Data...")
        
        if self.dry_run:
            logger.info("   [DRY RUN] Would deep sync")
            self.results["deep_sync"] = 0
            return
        
        try:
            count = asyncio.run(deep_sync_horse_data())
            self.results["deep_sync"] = count
            logger.info(f"   ✅ Deep synced {count} horses")
        except Exception as e:
            logger.error(f"   ❌ Deep sync failed: {e}")
            self.results["errors"].append(f"deep_sync: {e}")
    
    def log_summary(self):
        """Log pipeline summary"""
        logger.info("\n" + "=" * 60)
        logger.info("📊 PIPELINE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  Fixtures:    {self.results['fixtures']}")
        logger.info(f"  Racecards:   {self.results['racecards']}")
        logger.info(f"  Race Results:{self.results['race_results']}")
        logger.info(f"  Deep Sync:   {self.results['deep_sync']}")
        
        if self.results["errors"]:
            logger.warning(f"  Errors:      {len(self.results['errors'])}")
            for err in self.results["errors"]:
                logger.warning(f"    - {err}")
        else:
            logger.info("  Status:      ✅ ALL SUCCESS")
        
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="HKJC Data Pipeline")
    parser.add_argument(
        "--pipeline", 
        type=str, 
        default="all",
        choices=["all", "future", "history", "fixtures", "racecards", "deep-sync"],
        help="Pipeline to run"
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Run without making changes"
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Specific date for racecards (YYYY-MM-DD)"
    )
    
    args = parser.parse_args()
    
    runner = PipelineRunner(dry_run=args.dry_run)
    success = runner.run(args.pipeline)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
