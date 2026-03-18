"""
HKJC Data Pipeline - Application CronJob (Standalone)
=====================================================
独立运行的每日数据同步与模型训练系统

设计原则:
- 独立于 OpenClaw 运行
- 使用系统 cron 或 launchd 触发
- 所有操作使用 Upsert (Delta Change)，禁止 Delete + Insert
- 最后自动训练模型并 push 到 GitHub

Usage:
    python3 daily_pipeline.py                    # 完整流程
    python3 daily_pipeline.py --skip-training    # 跳过模型训练
    python3 daily_pipeline.py --dry-run          # 测试运行
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import os

# Add project to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import DatabaseConnection
from src.pipeline.fixtures import sync_fixtures, get_next_fixture, get_past_fixtures
from src.pipeline.racecards import scrape_next_racecards, scrape_race_day
from src.pipeline.history import sync_past_race_results, get_race_gaps
from src.pipeline.deep_sync import sync_single_horse, get_horses_needing_sync
from src.pipeline.completeness import completeness_check_and_sync

# ============================================================================
# LOGGING SETUP
# ============================================================================

LOG_DIR = PROJECT_ROOT / "logs" / "pipeline"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================================
# PART 1: FUTURE RACE PREPARATION
# ============================================================================

class FutureRacePipeline:
    """
    第一部分：未来比赛预测准备
    
    1. Sync fixtures (比赛日历)
    2. 检查今日日期，得到下一次比赛时间
    3. 用日期作为参数抓取 racecard 排位表
    4. 把 racecards 和 racecard_entries 存入 MongoDB
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.results = {
            "fixtures": 0,
            "racecards": 0,
            "races_scraped": []
        }
    
    def run(self) -> bool:
        """执行未来比赛准备流程"""
        logger.info("=" * 70)
        logger.info("🏃 PART 1: FUTURE RACE PREPARATION")
        logger.info("=" * 70)
        
        # Step 1: Sync fixtures
        self._sync_fixtures()
        
        # Step 2: Get next race day
        next_race = self._get_next_race_day()
        
        if not next_race:
            logger.warning("⚠️ 没有找到未来的比赛日")
            return False
        
        # Step 3 & 4: Scrape racecards
        self._scrape_racecards(next_race)
        
        self._log_summary()
        return len(self.results.get("errors", [])) == 0
    
    def _sync_fixtures(self):
        """1. 同步比赛日历 fixtures"""
        logger.info("\n📅 Step 1: 同步比赛日历 (Fixtures)")
        
        if self.dry_run:
            logger.info("   [DRY RUN] 跳过 fixture 同步")
            return
        
        try:
            # Use existing fixture module
            count = asyncio.run(sync_fixtures())
            self.results["fixtures"] = count
            logger.info(f"   ✅ 同步了 {count} 个比赛日")
            
        except Exception as e:
            logger.error(f"   ❌ Fixture 同步失败: {e}")
            self.results.setdefault("errors", []).append(str(e))
    
    def _get_next_race_day(self):
        """2. 获取下一次比赛日"""
        logger.info("\n🏇 Step 2: 获取下一次比赛日")
        
        try:
            # Use existing fixture module
            fixture = get_next_fixture()
            
            if fixture:
                logger.info(f"   找到下次比赛: {fixture['date']} ({fixture['venue']})")
                return fixture
            else:
                logger.warning("   没有找到未来的比赛日")
                return None
                
        except Exception as e:
            logger.error(f"   ❌ 获取下次比赛失败: {e}")
            return None
    
    def _scrape_racecards(self, fixture: dict):
        """3 & 4. 抓取排位表并存入 MongoDB (Idempotent)"""
        logger.info("\n🏇 Step 3 & 4: 抓取排位表")
        
        race_date = fixture["date"]
        venue = fixture.get("venue", "ST")
        status = fixture.get("scrape_status", "pending")
        
        # Idempotency: skip if already completed
        if status == "completed":
            logger.info(f"   ⏭️  {race_date} ({venue}) 已完成，跳过")
            self.results["racecards"] = fixture.get("race_count", 0)
            return
        
        if self.dry_run:
            logger.info(f"   [DRY RUN] 跳过 racecard 抓取 {race_date} {venue}")
            return
        
        try:
            # Connect to check existing racecards count
            db = DatabaseConnection()
            if not db.connect():
                logger.error("   ❌ Cannot connect to MongoDB")
                return
            
            existing = db.db["racecards"].count_documents({
                "race_date": race_date,
                "venue": venue
            })
            
            if existing >= fixture.get("race_count", 0) and fixture.get("race_count", 0) > 0:
                logger.info(f"   ✅ {race_date} ({venue}) 已有 {existing} 場 racecards，直接標記完成")
                db.db["fixtures"].update_one(
                    {"date": race_date, "venue": venue},
                    {"$set": {"scrape_status": "completed"}}
                )
                db.disconnect()
                self.results["racecards"] = existing
                return
            
            db.disconnect()
            
            # Scrape from HKJC
            count = asyncio.run(scrape_race_day(race_date, venue))
            
            if count > 0:
                # Mark as completed
                db2 = DatabaseConnection()
                db2.connect()
                db2.db["fixtures"].update_one(
                    {"date": race_date, "venue": venue},
                    {"$set": {"scrape_status": "completed"}}
                )
                db2.disconnect()
                logger.info(f"   ✅ 抓取了 {count} 场赛事並標記完成")
            else:
                logger.warning(f"   ⚠️ 未能抓取 {race_date} ({venue}) 的 racecards")
            
            self.results["racecards"] = count

        except Exception as e:
            logger.error(f"   ❌ Racecard 抓取失败: {e}")
            self.results.setdefault("errors", []).append(str(e))
            # Reset status to pending so it will retry next run
            try:
                db = DatabaseConnection()
                if db.connect():
                    db.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "pending"}}
                    )
                    db.disconnect()
            except Exception:
                pass
    
    def _log_summary(self):
        logger.info("\n" + "=" * 70)
        logger.info("📊 PART 1 完成")
        logger.info(f"   Fixtures: {self.results['fixtures']}")
        logger.info(f"   Racecards: {self.results['racecards']} 场")
        logger.info("=" * 70)


# ============================================================================
# PART 2: HISTORICAL OPTIMIZATION
# ============================================================================

class HistoricalOptimizationPipeline:
    """
    第二部分：过去比赛预测模型优化
    
    1. 检查今日日期，得到上一次比赛日期
    2. 检查 race_history 是否有上一次比赛日期的所有场次
    3. 把 missing 的赛果用 localresult link 抓取
    4. 每一场结果同时抓取马匹详细资料 (upsert delta change)
    5. 把新的 race_history 喂给预测模型，生成新模型并 push 到 GitHub
    """
    
    def __init__(self, dry_run: bool = False, skip_training: bool = False):
        self.dry_run = dry_run
        self.skip_training = skip_training
        self.db = DatabaseConnection()
        self.results = {
            "past_race_date": None,
            "venue": None,
            "expected_races": 0,
            "found_races": 0,
            "missing_races": [],
            "scraped_results": 0,
            "horses_synced": [],
            "model_trained": False,
            "errors": []
        }
    
    def run(self) -> bool:
        """执行历史优化流程"""
        logger.info("=" * 70)
        logger.info("📈 PART 2: HISTORICAL OPTIMIZATION")
        logger.info("=" * 70)
        
        # Step 1: Get past race day
        past_race = self._get_past_race_day()
        
        if not past_race:
            logger.info("ℹ️ 没有找到过去的比赛日 (可能今天没有比赛)")
            return True
        
        # Step 2: Gap analysis
        missing = self._gap_analysis(past_race)
        
        if not missing:
            logger.info("✅ 过去比赛数据完整，无需抓取")
        else:
            # Step 3 & 4: Scrape missing results + horse data
            self._scrape_and_sync(missing)
        
        # Step 5: Train model (if new data)
        if not self.skip_training:
            self._train_model()
        
        self._log_summary()
        return len(self.results.get("errors", [])) == 0
    
    def _get_past_race_day(self):
        """1. 获取上一次比赛日"""
        logger.info("\n🔍 Step 1: 获取上一次比赛日")
        
        try:
            # Use existing fixture module
            fixtures = get_past_fixtures(days_back=30)
            
            if not fixtures:
                logger.info("   没有找到过去的比赛日")
                return None
            
            # Get the most recent past fixture
            fixture = fixtures[0]  # Already sorted by date desc
            
            logger.info(f"   上次比赛: {fixture['date']} ({fixture['venue']})")
            self.results["past_race_date"] = fixture["date"]
            self.results["venue"] = fixture["venue"]
            self.results["expected_races"] = fixture.get("race_count", 8)
            
            return fixture
                
        except Exception as e:
            logger.error(f"   ❌ 获取上次比赛失败: {e}")
            return None
    
    def _gap_analysis(self, fixture: dict) -> list:
        """2. 检查缺失的赛果"""
        logger.info("\n🔍 Step 2: Gap Analysis - 检查缺失赛果")
        
        race_date = fixture["date"]
        venue = fixture["venue"]
        expected = fixture.get("race_count", 8)
        
        if not self.db.connect():
            return []
        
        try:
            # Count existing results
            found = self.db.db["races"].count_documents({
                "race_date": race_date,
                "venue": venue
            })
            
            self.results["found_races"] = found
            
            logger.info(f"   期望: {expected} 场, 已有: {found} 场")
            
            # Find missing race numbers
            existing = list(self.db.db["races"].find(
                {"race_date": race_date, "venue": venue},
                {"race_no": 1}
            ))
            existing_nos = [r["race_no"] for r in existing]
            
            missing = [i for i in range(1, expected + 1) if i not in existing_nos]
            
            if missing:
                logger.info(f"   缺失: 第 {missing} 场")
            else:
                logger.info("   ✅ 数据完整")
            
            self.results["missing_races"] = missing
            return missing
            
        finally:
            self.db.disconnect()
    
    def _scrape_and_sync(self, missing_races: list):
        """3 & 4. 抓取缺失赛果 + 马匹详细数据 (使用 Upsert)"""
        logger.info("\n🔄 Step 3 & 4: 抓取缺失赛果 + 马匹详细数据")
        
        race_date = self.results["past_race_date"]
        venue = self.results["venue"]
        
        for race_no in missing_races:
            logger.info(f"   抓取场次: {race_date} {venue} 第 {race_no} 场")
            
            if self.dry_run:
                continue
            
            # Scrape race result (use existing history module)
            result = self._scrape_race(race_date, venue, race_no)
            
            if result:
                self._upsert_race_result(race_date, venue, race_no, result)
                self.results["scraped_results"] += 1
                
                # Scrape horse data for each horse
                horses = result.get("horses", [])
                for horse in horses:
                    horse_id = horse.get("horse_id")
                    if horse_id:
                        self._upsert_horse_data(horse_id)
                        self.results["horses_synced"].append(horse_id)
            
            import time
            time.sleep(2)  # Rate limit
    
    def _scrape_race(self, race_date: str, venue: str, race_no: int) -> dict:
        """抓取单场赛果"""
        try:
            from src.crawler.race_results_scraper import RaceResultsScraper
            
            async def scrape():
                async with RaceResultsScraper(headless=True) as scraper:
                    return await scraper.scrape_race(race_date.replace("-", "/"), venue, race_no)
            
            return asyncio.run(scrape())
            
        except Exception as e:
            logger.error(f"   ❌ 抓取失败: {e}")
            self.results.setdefault("errors", []).append(f"scrape {race_no}: {e}")
            return None
    
    def _upsert_race_result(self, race_date: str, venue: str, race_no: int, result: dict):
        """Upsert 赛果 (Delta Change)"""
        race_id = f"{race_date.replace('-', '_')}_{venue}_{race_no}"
        
        if not self.db.connect():
            return
        
        try:
            doc = {
                "race_id": race_id,
                "race_date": race_date,
                "venue": venue,
                "race_no": race_no,
                "result": result.get("results"),
                "payouts": result.get("payouts"),
                "scrape_time": datetime.now().isoformat()
            }
            
            # UPSERT - not delete + insert!
            self.db.db["races"].update_one(
                {"race_id": race_id},
                {"$set": doc},
                upsert=True
            )
            
            logger.info(f"   ✅ Upsert 赛果: {race_id}")
            
        finally:
            self.db.disconnect()
    
    def _upsert_horse_data(self, horse_id: str):
        """Upsert 马匹详细数据 (Delta Change) - 使用现有模块"""
        
        if self.dry_run:
            logger.info(f"   [DRY RUN] 跳过马匹数据: {horse_id}")
            return
        
        try:
            # Use existing deep_sync module
            success = asyncio.run(sync_single_horse(horse_id))
            
            if success:
                logger.info(f"   ✅ Upsert 马匹数据: {horse_id}")
            
        except Exception as e:
            logger.error(f"   ❌ 马匹数据失败 {horse_id}: {e}")
            self.results.setdefault("errors", []).append(f"horse {horse_id}: {e}")
    
    def _train_model(self):
        """5. 训练模型并 Push 到 GitHub"""
        logger.info("\n🤖 Step 5: 训练预测模型")
        
        if self.results["scraped_results"] == 0 and not self.results["horses_synced"]:
            logger.info("   ℹ️ 没有新数据，跳过模型训练")
            return
        
        if self.dry_run:
            logger.info("   [DRY RUN] 跳过模型训练")
            return
        
        try:
            # Run training script
            train_script = PROJECT_ROOT / "train_model_v4.py"
            
            if not train_script.exists():
                logger.warning("   ⚠️ 训练脚本不存在")
                return
            
            logger.info("   运行训练...")
            result = subprocess.run(
                ["python3", str(train_script)],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                self.results["model_trained"] = True
                logger.info("   ✅ 模型训练完成")
                
                # Git commit and push
                self._git_push()
            else:
                logger.error(f"   ❌ 训练失败: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("   ❌ 训练超时")
        except Exception as e:
            logger.error(f"   ❌ 训练异常: {e}")
    
    def _git_push(self):
        """Git commit and push"""
        try:
            logger.info("   📤 Git commit and push...")
            
            # Add changes
            subprocess.run(["git", "add", "-A"], cwd=PROJECT_ROOT, check=True)
            
            # Commit with message
            date = datetime.now().strftime("%Y-%m-%d %H:%M")
            msg = f"Auto-update: model training {date}"
            
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True
            )
            
            # Push
            subprocess.run(
                ["git", "push"],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True
            )
            
            logger.info("   ✅ 已推送到 GitHub")
            
        except subprocess.CalledProcessError as e:
            logger.warning(f"   ⚠️ Git 操作失败: {e}")
        except Exception as e:
            logger.warning(f"   ⚠️ Git 异常: {e}")
    
    def _log_summary(self):
        logger.info("\n" + "=" * 70)
        logger.info("📊 PART 2 完成")
        logger.info(f"   上次比赛日期: {self.results['past_race_date']}")
        logger.info(f"   期望场次: {self.results['expected_races']}")
        logger.info(f"   已有场次: {self.results['found_races']}")
        logger.info(f"   缺失场次: {len(self.results['missing_races'])}")
        logger.info(f"   新抓取赛果: {self.results['scraped_results']}")
        logger.info(f"   同步马匹数: {len(self.results['horses_synced'])}")
        logger.info(f"   模型已训练: {self.results['model_trained']}")
        if self.results.get("errors"):
            logger.warning(f"   错误数: {len(self.results['errors'])}")
        logger.info("=" * 70)


# ============================================================================
# MAIN RUNNER
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="HKJC Daily Pipeline - 独立运行的每日数据同步与模型训练"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="测试运行，不实际抓取或修改数据"
    )
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="跳过模型训练步骤"
    )
    parser.add_argument(
        "--part",
        type=int,
        choices=[1, 2, 3],
        help="只运行指定部分 (1=未来比赛, 2=历史优化, 3=马匹资料完整性检查)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Part 3: 检查过去多少日的赛事的马匹完整性 (default 30)"
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Part 3: 只检查不加入同步队列"
    )
    
    args = parser.parse_args()
    
    logger.info("🚀 HKJC Daily Pipeline 启动")
    logger.info(f"   时间: {datetime.now()}")
    logger.info(f"   Dry Run: {args.dry_run}")
    logger.info(f"   Skip Training: {args.skip_training}")
    
    success = True
    
    # Part 1: Future Race
    if args.part is None or args.part == 1:
        future = FutureRacePipeline(dry_run=args.dry_run)
        success = future.run() and success
    
    # Part 2: Historical
    if args.part is None or args.part == 2:
        history = HistoricalOptimizationPipeline(
            dry_run=args.dry_run,
            skip_training=args.skip_training
        )
        success = history.run() and success
    
    # Part 3: Horse data completeness check
    if args.part is None or args.part == 3:
        logger.info(f"\n🐴 Starting Part 3 (days_back={args.days_back}, skip_sync={args.skip_sync})")
        part3_results = asyncio.run(completeness_check_and_sync(
            days_back=args.days_back,
            dry_run=args.dry_run,
            skip_sync=args.skip_sync,
        ))
        logger.info(f"Part 3 results: {part3_results}")
    
    # Final summary
    logger.info("\n" + "=" * 70)
    if success:
        logger.info("✅ Daily Pipeline 完成!")
    else:
        logger.error("❌ Pipeline 有错误")
    logger.info("=" * 70)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
