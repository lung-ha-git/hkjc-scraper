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
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import DatabaseConnection
from src.pipeline.fixtures import sync_fixtures, get_next_fixture, get_past_fixtures
from src.pipeline.racecards import scrape_next_racecards, scrape_race_day
from src.pipeline.history import sync_past_race_results, get_race_gaps
from src.pipeline.deep_sync import sync_single_horse, get_horses_needing_sync
from src.pipeline.completeness import completeness_check_and_sync
from src.pipeline.entry_validator import run_validation
from src.scheduler.queue_worker import QueueWorker

# ============================================================================
# LOGGING SETUP
# ============================================================================

LOG_DIR = PROJECT_ROOT / "logs" / "pipeline"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# NOTE: basicConfig() must come AFTER all imports to avoid child modules'
# basicConfig(level=INFO) calls (which have no handlers) preempting our FileHandler.
# See: https://docs.python.org/3/library/logging.html#logging.basicConfig
# "basicConfig() does nothing if the root logger already has handlers configured."
# NOTE: basicConfig() must come AFTER all imports to avoid child modules'
# basicConfig(level=INFO) calls (which have no handlers) preempting our FileHandler.
# See: https://docs.python.org/3/library/logging.html#logging.basicConfig
# "basicConfig() does nothing if the root logger already has handlers configured."
FMT = '%(asctime)s - %(levelname)s - %(message)s'
FILE_LOG = LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format=FMT,
    handlers=[logging.FileHandler(FILE_LOG), logging.StreamHandler()]
)

# Apply format to ALL existing handlers (child modules may have added
# StreamHandlers without a format during import, making basicConfig() a no-op).
_root = logging.getLogger()
_formatter = logging.Formatter(FMT)
for h in _root.handlers:
    h.setFormatter(_formatter)

# Ensure FileHandler is present
_root_has_file = any(isinstance(h, logging.FileHandler) for h in _root.handlers)
if not _root_has_file:
    fh = logging.FileHandler(FILE_LOG)
    fh.setFormatter(_formatter)
    _root.addHandler(fh)

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
    
    def __init__(self, dry_run: bool = False, force_racecards: bool = False):
        self.dry_run = dry_run
        self.force_racecards = force_racecards
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
        
        # Step 2 & 3 & 4: Scrape racecards for ALL upcoming fixtures (both HV and ST)
        # Uses scrape_next_racecards() which loops through ALL pending fixtures
        from src.pipeline.racecards import scrape_next_racecards
        count = asyncio.run(scrape_next_racecards())
        self.results["racecards"] = count
        
        # Step 5: FEAT-006 - Validate racecard entries (only on race day, both HV and ST)
        # Re-use the same fixture logic for each today fixture
        today_str = dt.now().strftime("%Y-%m-%d")
        db = DatabaseConnection()
        db.connect()
        today_fixtures = list(db.db["fixtures"].find({ 
            "date": today_str,
            "scrape_status": {"$in": ["completed", "race_day"]}
        }))
        db.disconnect()
        for fix in today_fixtures:
            self._validate_entries(fix)
        
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
        """3 & 4. 抓取排位表并存入 MongoDB (Idempotent - daily update for upcoming races)"""
        logger.info("\n🏇 Step 3 & 4: 抓取排位表")
        
        race_date = fixture["date"]
        venue = fixture.get("venue", "ST")
        status = fixture.get("scrape_status", "pending")
        
        # Always re-scrape upcoming races (racecards can change daily - scratchings, weights)
        # Only skip past/completed races that are NOT upcoming
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        is_future = race_date >= today
        
        if status == "completed" and not is_future:
            logger.info(f"   ⏭️  {race_date} ({venue}) 已完成且非未來賽事，跳过")
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
            
            if self.force_racecards:
                logger.info(f"   🔄 --force-racecards: 強制重抓")
            elif existing >= fixture.get("race_count", 0) and fixture.get("race_count", 0) > 0:
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
                # No racecards found - could be not published yet OR it's race day
                # HKJC publishes racecards around noon the day BEFORE the race
                # If today is race day, racecards won't appear - mark as race_day (no more retries needed)
                from datetime import datetime as dt
                today_str = dt.now().strftime("%Y-%m-%d")
                is_race_day = (race_date == today_str)
                
                if is_race_day:
                    db3 = DatabaseConnection()
                    db3.connect()
                    db3.db["fixtures"].update_one(
                        {"date": race_date, "venue": venue},
                        {"$set": {"scrape_status": "race_day"}}
                    )
                    db3.disconnect()
                    logger.info(f"   ℹ️  {race_date} ({venue}) 是賽日當天，排位表已截止，標記為 race_day")
                else:
                    logger.warning(f"   ⚠️ 未能抓取 {race_date} ({venue}) 的 racecards（可能尚未發布，明天再試）")
                    # Keep status as pending - will retry tomorrow
            
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

    def _validate_entries(self, fixture: dict):
        """5. FEAT-006: Validate racecard entries vs odds page (only on race day)"""
        race_date = fixture["date"]
        venue = fixture.get("venue", "ST")
        
        # Only validate on race day (when entries are finalized)
        from datetime import datetime as dt
        today_str = dt.now().strftime("%Y-%m-%d")
        is_race_day = (race_date == today_str)
        
        if not is_race_day:
            logger.info(f"\n🔍 Step 5 (FEAT-006): 跳過驗證 (非賽日: {race_date})")
            return
        
        logger.info(f"\n🔍 Step 5 (FEAT-006): 驗證 Racecard vs 即時賠率頁面馬匹")
        logger.info(f"   賽日: {race_date} ({venue})")
        
        if self.dry_run:
            logger.info("   [DRY RUN] 跳過驗證")
            return
        
        try:
            import asyncio
            result = asyncio.run(run_validation(race_date, venue))
            
            summary = result.get("summary", {})
            self.results["entry_validation"] = summary
            
            if summary.get("races_with_changes", 0) > 0:
                logger.warning(f"   ⚠️ 發現 {summary['races_with_changes']} 場有馬匹變動!")
                logger.warning(f"      新增: {summary.get('total_added', 0)}")
                logger.warning(f"      移除: {summary.get('total_removed', 0)}")
                logger.warning(f"      替補: {summary.get('total_substituted', 0)}")
                logger.warning(f"      變更: {summary.get('total_changed', 0)}")
            else:
                logger.info(f"   ✅ 所有場次馬匹資料一致")
                
        except Exception as e:
            logger.error(f"   ❌ 驗證失敗: {e}")
            self.results.setdefault("errors", []).append(f"validation: {e}")

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
    
    1. 获取过去 N 日内所有比赛日期
    2. 对每个比赛日检查缺失的赛果
    3. 把 missing 的赛果用 localresult link 抓取
    4. 每一场结果同时抓取马匹详细资料 (upsert delta change)
    5. 把新的 race_history 喂给预测模型，生成新模型并 push 到 GitHub
    """
    
    def __init__(self, dry_run: bool = False, skip_training: bool = False, days_back: int = 30):
        self.dry_run = dry_run
        self.skip_training = skip_training
        self.days_back = days_back
        self.db = DatabaseConnection()
        self.results = {
            "total_fixtures": 0,
            "fixtures_with_missing": 0,
            "total_expected_races": 0,
            "total_existing_races": 0,
            "total_missing_races": [],
            "scraped_results": 0,
            "unique_horses_synced": set(),
            "model_trained": False,
            "errors": []
        }
    
    def run(self) -> bool:
        """执行历史优化流程"""
        logger.info("=" * 70)
        logger.info("📈 PART 2: HISTORICAL OPTIMIZATION")
        logger.info("=" * 70)
        
        # Step 1: Get ALL past race days
        past_fixtures = self._get_all_past_fixtures()
        
        if not past_fixtures:
            logger.info("ℹ️ 没有找到过去的比赛日")
            return True
        
        self.results["total_fixtures"] = len(past_fixtures)
        
        # Step 2: Process each past fixture
        for fixture in past_fixtures:
            race_date = fixture["date"]
            venue = fixture.get("venue", "ST")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"  处理: {race_date} ({venue})")
            logger.info(f"{'='*60}")
            
            # Gap analysis for this fixture
            missing = self._gap_analysis(fixture)
            
            if not missing:
                logger.info(f"   ✅ 数据完整，跳过")
            else:
                self.results["fixtures_with_missing"] += 1
                # Scrape missing results + horse data
                scraped = self._scrape_and_sync(race_date, venue, missing)
                self.results["scraped_results"] += scraped
        
        # Step 3: Train model (if new data)
        if not self.skip_training:
            self._train_model()
        
        self._log_summary()
        return len(self.results.get("errors", [])) == 0
    
    def _get_all_past_fixtures(self) -> list:
        """获取所有过去的比赛日"""
        logger.info(f"\n🔍 Step 1: 获取过去 {self.days_back} 日内所有比赛日...")
        
        try:
            fixtures = get_past_fixtures(days_back=self.days_back)
            logger.info(f"   找到 {len(fixtures)} 个过去的比赛日")
            for f in fixtures:
                logger.info(f"   - {f['date']} ({f.get('venue','?')}): {f.get('race_count',0)} 场")
            return fixtures
        except Exception as e:
            logger.error(f"   ❌ 获取过去比赛日失败: {e}")
            return []
    
    def _get_actual_race_count(self, race_date: str, venue: str) -> int:
        """从 HKJC results page 获取实际场次数量"""
        import re
        import urllib.request
        import urllib.error
        
        url = f"https://racing.hkjc.com/zh-hk/local/information/localresults?racedate={race_date.replace('-', '/')}"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                content = response.read().decode('utf-8', errors='replace')
            
            # Find all RaceNo= patterns in links (more reliable than 第X場 which is JS-rendered)
            race_nos = re.findall(r'RaceNo=(\d+)', content)
            
            if race_nos:
                actual_count = max(int(r) for r in race_nos)
                logger.info(f"   📊 实际场次: {actual_count} (from RaceNo links)")
                return actual_count
            else:
                # Fallback: try 第X場 pattern
                race_nums = re.findall(r'第\s*(\d+)\s*場', content)
                if race_nums:
                    actual_count = max(int(r) for r in race_nums)
                    logger.info(f"   📊 实际场次: {actual_count} (from 第X場)")
                    return actual_count
                
                # No races found - likely future date
                logger.warning(f"   ⚠️ 无法从 results page 获取场次 (可能当日无赛事的未来日期)")
                return 0
                
        except urllib.error.HTTPError as e:
            logger.warning(f"   ⚠️ HTTP error {e.code} 获取场次: {race_date}")
            return 0
        except Exception as e:
            logger.warning(f"   ⚠️ 获取场次失败: {e}")
            return 0
    
    def _gap_analysis(self, fixture: dict) -> list:
        """检查单个赛果日的缺失场次"""
        race_date = fixture["date"]
        venue = fixture.get("venue", "ST")
        
        # Get actual race count from results page (more reliable than fixture.race_count)
        expected = self._get_actual_race_count(race_date, venue)
        
        # If 0 races, likely future date - skip this fixture
        if expected == 0:
            logger.info(f"   跳过 (当日无赛事，可能是未来日期)")
            return []
        
        self.results["total_expected_races"] += expected
        
        if not self.db.connect():
            return []
        
        try:
            # Count existing results
            found = self.db.db["races"].count_documents({
                "race_date": race_date,
                "venue": venue
            })
            
            self.results["total_existing_races"] += found
            
            logger.info(f"   期望: {expected} 场, 已有: {found} 场")
            
            # Find missing race numbers (race_no stored as int in races collection)
            existing = list(self.db.db["races"].find(
                {"race_date": race_date, "venue": venue},
                {"race_no": 1}
            ))
            existing_nos = {int(r["race_no"]) for r in existing}
            
            missing = [i for i in range(1, expected + 1) if i not in existing_nos]
            
            if missing:
                logger.info(f"   缺失: 第 {missing} 场")
                self.results["total_missing_races"].append(
                    {"date": race_date, "venue": venue, "missing": missing}
                )
            else:
                logger.info(f"   ✅ 数据完整")
            
            return missing
            
        finally:
            self.db.disconnect()
    
    def _scrape_and_sync(self, race_date: str, venue: str, missing_races: list) -> int:
        """抓取缺失赛果 + 马匹详细数据"""
        logger.info(f"\n🔄 抓取 {race_date} ({venue}) 缺失场次...")
        
        scraped_count = 0
        
        for race_no in missing_races:
            logger.info(f"   抓取场次: {race_date} {venue} 第 {race_no} 场")
            
            if self.dry_run:
                scraped_count += 1  # Count in dry-run too
                continue
            
            # Scrape race result
            result = self._scrape_race(race_date, venue, race_no)
            
            if result:
                self._upsert_race_result(race_date, venue, race_no, result)
                scraped_count += 1
                
                # Scrape horse data for each horse
                horses = result.get("horses", [])
                for horse in horses:
                    horse_id = horse.get("horse_id")
                    if horse_id:
                        self._upsert_horse_data(horse_id)
                        self.results["unique_horses_synced"].add(horse_id)
            
            import time
            time.sleep(2)  # Rate limit
        
        return scraped_count
    
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
            meta = result.get("metadata", {})
            hkjc_race_id = race_id  # Same format: 2026_04_08_HV_1
            doc = {
                "race_id": race_id,
                "hkjc_race_id": hkjc_race_id,
                "race_date": race_date,
                "venue": venue,
                "race_no": race_no,
                "class": meta.get("class"),
                "distance": meta.get("distance"),
                "track_condition": meta.get("track"),
                "prize": meta.get("prize"),
                "results": result.get("results"),
                "payout": result.get("payout"),
                "created_at": datetime.now().isoformat(),
                "modified_at": datetime.now().isoformat(),
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
        """5. Online learning model update - incremental training"""
        logger.info("\n🤖 Step 5: 在线学习模型更新")
        
        if self.results["scraped_results"] == 0 and len(self.results["unique_horses_synced"]) == 0:
            logger.info("   ℹ️ 没有新数据，跳过模型训练")
            return
        
        if self.dry_run:
            logger.info("   [DRY RUN] 跳过模型训练")
            return
        
        try:
            # Try online learning (incremental update) first
            from src.ml.online_trainer import run_daily_update
            
            logger.info("   运行增量学习更新...")
            success = run_daily_update()
            
            if success:
                self.results["model_trained"] = True
                logger.info("   ✅ 增量模型更新完成")
                # Save timestamped backup for download
                self._save_timestamped_models()
                return
            else:
                logger.warning("   增量更新失败，尝试完整训练...")
                
        except Exception as e:
            logger.warning(f"   在线学习模块出错: {e}, 回退到完整训练")
        
        # Fallback: Full retraining
        try:
            train_script = PROJECT_ROOT / "train_ensemble.py"
            
            if not train_script.exists():
                logger.warning("   ⚠️ 训练脚本不存在")
                return
            
            logger.info("   运行完整训练...")
            result = subprocess.run(
                ["python3", str(train_script), "--days", "365"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                self.results["model_trained"] = True
                logger.info("   ✅ 完整模型训练完成")
                # Save timestamped backup for download
                self._save_timestamped_models()
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
    
    def _save_timestamped_models(self):
        """Save timestamped copies of trained models for download"""
        try:
            models_dir = PROJECT_ROOT / "models"
            if not models_dir.exists():
                logger.warning("   ⚠️ Models directory not found")
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Save timestamped copies
            for f in models_dir.glob("*.pkl"):
                ts_name = f"{f.stem}_{timestamp}{f.suffix}"
                ts_path = models_dir / ts_name
                import shutil
                shutil.copy2(f, ts_path)
                logger.info(f"   📦 Saved: {ts_name}")
            
            # Keep only last 7 days of timestamped models
            import time
            cutoff = time.time() - 7 * 24 * 60 * 60
            for f in models_dir.glob("*_[0-9]*_[0-9]*.pkl"):
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    logger.info(f"   🗑️ Removed old: {f.name}")
            
            logger.info("   📥 模型已就緒，可通過 /models/downloads 下載")
        except Exception as e:
            logger.warning(f"   ⚠️ 保存時間戳模型失敗: {e}")
    
    def _log_summary(self):
        logger.info("\n" + "=" * 70)
        logger.info("📊 PART 2 完成")
        logger.info(f"   处理赛日: {self.results['total_fixtures']} 个")
        logger.info(f"   有缺失赛日: {self.results['fixtures_with_missing']} 个")
        logger.info(f"   期望场次: {self.results['total_expected_races']}")
        logger.info(f"   已有场次: {self.results['total_existing_races']}")
        logger.info(f"   缺失场次总数: {sum(len(m['missing']) for m in self.results['total_missing_races'])}")
        logger.info(f"   新抓取赛果: {self.results['scraped_results']}")
        logger.info(f"   同步马匹数: {len(self.results['unique_horses_synced'])}")
        logger.info(f"   模型已训练: {self.results['model_trained']}")
        if self.results.get("errors"):
            logger.warning(f"   错误数: {len(self.results['errors'])}")
        logger.info("=" * 70)


# ============================================================================
# PART 4: QUEUE WORKER
# ============================================================================

class QueueWorkerPipeline:
    """
    第四部分：处理 scrape_queue 中的马匹数据同步任务
    """
    
    def __init__(self, dry_run: bool = False, max_items: int = 50):
        self.dry_run = dry_run
        self.max_items = max_items
        self.results = {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "errors": []
        }
    
    def run(self) -> bool:
        """执行 queue worker"""
        logger.info("=" * 70)
        logger.info("🔄 PART 4: QUEUE WORKER")
        logger.info("=" * 70)
        
        if self.dry_run:
            logger.info("   [DRY RUN] 跳过 queue processing")
            return True
        
        try:
            from src.scheduler.queue_worker import QueueWorker
            
            worker = QueueWorker()
            
            if not worker.connect():
                logger.error("   ❌ Cannot connect to MongoDB")
                return False
            
            logger.info(f"   Processing up to {self.max_items} queue items...")
            
            # Process horse detail queue
            for i in range(self.max_items):
                job = worker.claim_next_job("scrape_queue")
                if not job:
                    logger.info(f"   ✅ No more pending jobs")
                    break
                
                self.results["processed"] += 1
                logger.info(f"   Processing: {job.get('horse_id', job.get('target_url'))}")
                
                # Process based on job type
                if job.get("type") == "horse_detail":
                    horse_id = job.get("horse_id")
                    try:
                        # Run async sync
                        import sys
                        sys.path.insert(0, str(PROJECT_ROOT))
                        from src.pipeline.deep_sync import sync_single_horse
                        result = asyncio.run(sync_single_horse(horse_id))
                        if result:
                            self.results["success"] += 1
                            logger.info(f"   ✅ Synced: {horse_id}")
                        else:
                            self.results["failed"] += 1
                            logger.warning(f"   ⚠️ Failed: {horse_id}")
                    except Exception as e:
                        self.results["failed"] += 1
                        self.results["errors"].append(str(e))
                        logger.error(f"   ❌ Error syncing {horse_id}: {e}")
                
                # Mark job as completed/failed
                status = "completed" if job.get("status") != "failed" else "failed"
                worker.db.db["scrape_queue"].update_one(
                    {"_id": job["_id"]},
                    {"$set": {"status": status, "processed_at": datetime.now().isoformat()}}
                )
                
                import time
                time.sleep(1)  # Rate limit
            
            worker.disconnect()
            
            self._log_summary()
            return self.results["failed"] == 0
            
        except Exception as e:
            logger.error(f"   ❌ Queue worker error: {e}")
            return False
    
    def _log_summary(self):
        logger.info("\n" + "=" * 70)
        logger.info("📊 PART 4 完成")
        logger.info(f"   处理: {self.results['processed']}")
        logger.info(f"   成功: {self.results['success']}")
        logger.info(f"   失败: {self.results['failed']}")
        if self.results.get("errors"):
            logger.warning(f"   错误: {len(self.results['errors'])}")
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
        choices=[1, 2, 3, 4],
        help="只运行指定部分 (1=未来比赛, 2=历史优化, 3=马匹资料完整性检查, 4=队列处理)"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=30,
        help="Part 2 & 3: 检查过去多少日的赛事 (default 30)"
    )
    parser.add_argument(
        "--force-racecards",
        action="store_true",
        help="Part 1: 強制重新抓取 racecards（忽略現有數據）"
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
    logger.info(f"   Force Racecards: {args.force_racecards}")
    logger.info(f"   Skip Training: {args.skip_training}")

    # Collect per-part results for MongoDB logging
    part_results = {}

    success = True

    # Part 1: Future Race
    if args.part is None or args.part == 1:
        future = FutureRacePipeline(dry_run=args.dry_run, force_racecards=args.force_racecards)
        part_results["part1"] = {"success": future.run(), "data": future.results}
        success = part_results["part1"]["success"] and success

    # Part 2: Historical
    if args.part is None or args.part == 2:
        history = HistoricalOptimizationPipeline(
            dry_run=args.dry_run,
            skip_training=args.skip_training,
            days_back=args.days_back,
        )
        part_results["part2"] = {"success": history.run(), "data": history.results}
        success = part_results["part2"]["success"] and success

    # Part 3: Horse data completeness check
    if args.part is None or args.part == 3:
        logger.info(f"\n🐴 Starting Part 3 (days_back={args.days_back}, skip_sync={args.skip_sync})")
        part3_data = asyncio.run(completeness_check_and_sync(
            days_back=args.days_back,
            dry_run=args.dry_run,
            skip_sync=args.skip_sync,
        ))
        part_results["part3"] = {"success": True, "data": part3_data}
        logger.info(f"Part 3 results: {part3_data}")

    # Part 4: Queue Worker
    if args.part is None or args.part == 4:
        logger.info(f"\n🔄 Starting Part 4: Queue Worker")
        queue = QueueWorkerPipeline(dry_run=args.dry_run, max_items=50)
        part_results["part4"] = {"success": queue.run(), "data": queue.results}

    # Final summary
    logger.info("\n" + "=" * 70)
    if success:
        logger.info("✅ Daily Pipeline 完成!")
    else:
        logger.error("❌ Pipeline 有错误")
    logger.info("=" * 70)

    # Log run summary to MongoDB
    _log_run_summary_to_mongodb(success, args, part_results)

    sys.exit(0 if success else 1)


def _log_run_summary_to_mongodb(success: bool, args, part_results: dict):
    """Write pipeline run summary to MongoDB for tracking & alerting"""
    try:
        from src.database.connection import DatabaseConnection
        db_conn = DatabaseConnection()
        if not db_conn.connect():
            logger.warning("Cannot connect to MongoDB for run logging")
            return

        # Extract key metrics from each part
        def safe_get(results, *keys, default=None):
            for k in keys:
                if isinstance(results, dict):
                    results = results.get(k, default)
                else:
                    return default
            return results

        doc = {
            "run_at": datetime.now().isoformat(),
            "success": success,
            "dry_run": args.dry_run,
            "parts_run": [p for p in [1, 2, 3] if args.part is None or args.part == p],
            "days_back": args.days_back,
            "log_file": str(LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"),

            # Part 1
            "part1_fixtures_synced": safe_get(part_results.get("part1", {}).get("data"), "fixtures", default=0),
            "part1_racecards_scraped": safe_get(part_results.get("part1", {}).get("data"), "racecards", default=0),

            # Part 2
            "part2_fixtures_processed": safe_get(part_results.get("part2", {}).get("data"), "total_fixtures", default=0),
            "part2_races_scraped": safe_get(part_results.get("part2", {}).get("data"), "scraped_results", default=0),
            "part2_horses_synced": len(safe_get(part_results.get("part2", {}).get("data"), "unique_horses_synced", default=set())) or 0,
            "part2_model_trained": safe_get(part_results.get("part2", {}).get("data"), "model_trained", default=False),
            "part2_errors": safe_get(part_results.get("part2", {}).get("data"), "errors", default=[]),

            # Part 3
            "part3_total_horses": safe_get(part_results.get("part3", {}).get("data"), "total_recent_horses", default=0),
            "part3_complete": safe_get(part_results.get("part3", {}).get("data"), "complete", default=0),
            "part3_incomplete": safe_get(part_results.get("part3", {}).get("data"), "incomplete", default=0),
            "part3_queued": safe_get(part_results.get("part3", {}).get("data"), "queued", default=0),
            "part3_missing_fields": safe_get(part_results.get("part3", {}).get("data"), "missing_by_field", default={}),
        }

        db_conn.db["pipeline_runs"].insert_one(doc)
        db_conn.disconnect()
        logger.info(f"✅ Run summary logged to MongoDB: pipeline_runs")
    except Exception as e:
        logger.warning(f"⚠️ Failed to log run summary to MongoDB: {e}")


if __name__ == "__main__":
    main()
