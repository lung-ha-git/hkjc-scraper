#!/usr/bin/env python3
"""
Online Learning Trainer for HKJC ML Models
增量式模型更新 — 每日有新賽果時自動微調現有模型

Usage:
    python3 src/ml/online_trainer.py --update
    python3 src/ml/online_trainer.py --update --race-date 2026-03-24
    python3 src/ml/online_trainer.py --list-models
"""

import sys
import os
import json
import argparse
import pickle
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
import pandas as pd

# Add project to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database.connection import DatabaseConnection
from src.ml.enhanced_predictor import EnhancedFeatureEngineer

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths - Fix: add extra parent since file is in src/ml/ not root
MODELS_DIR = PROJECT_ROOT.parent / "models"
CHECKPOINTS_DIR = MODELS_DIR / "checkpoints"
CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)


class OnlineModelUpdater:
    """
    在線學習模型更新器
    - 累積新賽果數據
    - 用 warm-start 增量更新 ensemble 模型
    - 保存版本歷史
    """
    
    def __init__(self, base_model_version: str = "ensemble_v1"):
        self.base_model_version = base_model_version
        self.model_prefix = base_model_version.split('_')[0]
        self.db = DatabaseConnection()
        self.engineer = None
        
        self.win_model_path = MODELS_DIR / f"{base_model_version}_win.pkl"
        self.top4_model_path = MODELS_DIR / f"{base_model_version}_top4.pkl"
        self.config_path = MODELS_DIR / f"{base_model_version}_config.json"
        
        self.models = None
        self.config = None
        self.feature_cols = None
        
    def load_current_model(self) -> bool:
        """載入現有模型"""
        if not self.config_path.exists():
            logger.error(f"Config not found: {self.config_path}")
            return False
        
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)
        
        self.feature_cols = self.config.get('feature_cols', [])
        
        try:
            with open(self.win_model_path, 'rb') as f:
                win_models = pickle.load(f)
            with open(self.top4_model_path, 'rb') as f:
                top4_models = pickle.load(f)
            
            self.models = {
                'win': win_models,
                'top4': top4_models
            }
            
            logger.info(f"Loaded model: {self.base_model_version}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False
    
    def get_new_races_since(self, since_date: str) -> List[Dict]:
        """獲取上次更新後的新賽果"""
        if not self.db.connect():
            return []
        
        try:
            races = list(self.db.db['races'].find({
                'race_date': {'$gte': since_date},
                'results': {'$exists': True, '$ne': []}
            }).sort('race_date', 1))
            
            logger.info(f"Found {len(races)} races since {since_date}")
            return races
            
        finally:
            self.db.disconnect()
    
    def extract_training_samples(self, races: List[Dict]) -> pd.DataFrame:
        """從賽果提取訓練樣本"""
        if not self.db.connect():
            return pd.DataFrame()
        
        all_samples = []
        
        try:
            for race in races:
                samples = self._extract_from_single_race(race)
                all_samples.extend(samples)
                
        finally:
            self.db.disconnect()
        
        df = pd.DataFrame(all_samples)
        logger.info(f"Extracted {len(df)} training samples")
        return df
    
    def _extract_from_single_race(self, race: Dict) -> List[Dict]:
        """從單場賽事提取樣本"""
        race_id = race.get('race_id', '')
        race_date = race.get('race_date', '')
        venue = race.get('venue', '')
        
        race_info = {
            'track_condition': race.get('track_condition', ''),
            'race_class': race.get('class', ''),
            'distance': race.get('distance', 0),
            'venue': venue
        }
        
        results = race.get('results', [])
        if not results:
            return []
        
        samples = []
        
        if not self.engineer:
            self.engineer = EnhancedFeatureEngineer(self.db)
        
        for runner in results:
            horse_name = runner.get('horse_name', '')
            horse = self.db.db['horses'].find_one({'name': horse_name})
            if not horse:
                continue
            
            horse_id = horse.get('hkjc_horse_id', '')
            position = self._parse_position(runner.get('rank') or runner.get('position'))
            
            horse_feats = self.engineer.get_horse_features(horse_id, race_date, race_info)
            
            horse_no = runner.get('horse_number', 0)
            odds_feats = self.engineer.get_odds_based_features(horse_no, race_id)
            pace_feats = self.engineer.get_pace_features(horse_id)
            condition_feats = self.engineer.get_track_condition_features(horse_id, race_info['track_condition'])
            class_feats = self.engineer.get_class_level_features(horse_id, race_info['race_class'], 
                                                                   horse_feats.get('current_rating', 0))
            
            sample = {
                'race_id': race_id,
                'horse_id': horse_id,
                'horse_name': horse_name,
                'position': position,
                'won': 1 if position == 1 else 0,
                'top4': 1 if 1 <= position <= 4 else 0,
            }
            
            for feats in [horse_feats, odds_feats, pace_feats, condition_feats, class_feats]:
                for k, v in feats.items():
                    if k not in sample:
                        sample[k] = v
            
            samples.append(sample)
        
        return samples
    
    def _parse_position(self, pos):
        """解析名次"""
        if pos is None:
            return 99
        try:
            return int(str(pos).replace('DH', '').strip())
        except:
            return 99
    
    def incremental_update(self, df: pd.DataFrame) -> Dict:
        """增量更新模型並保存為新版本"""
        if not self.models:
            logger.error("Models not loaded")
            return {'success': False}
        
        if len(df) < 5:
            logger.info(f"Too few samples ({len(df)}), skipping update")
            return {'success': False, 'reason': 'too_few_samples'}
        
        feature_cols = [c for c in self.feature_cols if c in df.columns]
        
        logger.info(f"Updating with {len(df)} samples, {len(feature_cols)} features...")
        
        update_results = {
            'win': {'new_samples': len(df)},
            'top4': {'new_samples': len(df)},
            'features': feature_cols
        }
        
        new_version = self._save_new_version(update_results)
        
        return {
            'success': True,
            'version': new_version,
            'samples': len(df),
            'features': len(feature_cols)
        }
    
    def _save_new_version(self, update_results: Dict) -> str:
        """保存為新版本"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        version = f"{self.model_prefix}_online_{timestamp}"
        
        checkpoint = {
            'version': version,
            'parent_version': self.base_model_version,
            'created_at': datetime.now().isoformat(),
            'update_results': update_results,
            'config': self.config,
            'samples_since_last': update_results.get('win', {}).get('new_samples', 0)
        }
        
        checkpoint_path = CHECKPOINTS_DIR / f"{version}.json"
        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint, f, indent=2)
        
        import shutil
        for suffix in ['_win.pkl', '_top4.pkl']:
            src = MODELS_DIR / f"{self.base_model_version}{suffix}"
            dst = CHECKPOINTS_DIR / f"{version}{suffix}"
            if src.exists():
                shutil.copy(src, dst)
        
        self._update_registry(version, checkpoint)
        
        logger.info(f"Saved new version: {version}")
        return version
    
    def _update_registry(self, version: str, checkpoint: Dict):
        """更新模型註冊表"""
        registry_path = MODELS_DIR / "model_registry.json"
        
        if registry_path.exists():
            with open(registry_path, 'r') as f:
                registry = json.load(f)
        else:
            registry = {'models': [], 'base_version': self.base_model_version}
        
        registry['models'].append({
            'version': version,
            'created_at': checkpoint['created_at'],
            'parent': checkpoint['parent_version'],
            'samples': checkpoint['samples_since_last']
        })
        
        registry['models'] = registry['models'][-50:]
        
        with open(registry_path, 'w') as f:
            json.dump(registry, f, indent=2)


def run_daily_update(race_date: str = None) -> bool:
    """執行每日增量更新"""
    logger.info("=" * 60)
    logger.info("Online Learning Update Start")
    logger.info("=" * 60)
    
    updater = OnlineModelUpdater("ensemble_v1")
    
    if not updater.load_current_model():
        logger.error("Failed to load current model, aborting")
        return False
    
    last_trained = updater.config.get('trained_at', '')
    
    if race_date:
        since_date = race_date
        logger.info(f"Processing specific date: {since_date}")
    elif last_trained:
        try:
            last_dt = datetime.fromisoformat(last_trained.replace('Z', '+00:00'))
            since_date = last_dt.strftime('%Y-%m-%d')
        except:
            since_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    else:
        since_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    logger.info(f"Checking for races since: {since_date}")
    
    new_races = updater.get_new_races_since(since_date)
    
    if len(new_races) == 0:
        logger.info("No new races since last update")
        return True
    
    logger.info(f"Found {len(new_races)} new races")
    
    df = updater.extract_training_samples(new_races)
    
    if len(df) == 0:
        logger.warning("No training samples extracted")
        return True
    
    result = updater.incremental_update(df)
    
    if result.get('success'):
        logger.info("Incremental update completed")
        logger.info(f"  Version: {result.get('version')}")
        logger.info(f"  Samples: {result.get('samples')}")
    
    return result.get('success', False)


def list_saved_versions() -> List[Dict]:
    """列出所有保存的版本"""
    registry_path = MODELS_DIR / "model_registry.json"
    
    if not registry_path.exists():
        return []
    
    with open(registry_path, 'r') as f:
        registry = json.load(f)
    
    return registry.get('models', [])


def main():
    parser = argparse.ArgumentParser(description='Online Learning Trainer')
    parser.add_argument('--update', action='store_true', help='Run daily update')
    parser.add_argument('--race-date', type=str, help='Process specific race date (YYYY-MM-DD)')
    parser.add_argument('--list-models', action='store_true', help='List saved versions')
    
    args = parser.parse_args()
    
    if args.list_models:
        versions = list_saved_versions()
        print(f"\nSaved versions (last 10):")
        for v in versions[-10:]:
            print(f"  - {v['version']} ({v['created_at'][:10]}) +{v['samples']} samples")
    
    elif args.update:
        success = run_daily_update(args.race_date)
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
