#!/usr/bin/env python3
"""
FEAT-014: Train Ensemble Model

Usage:
    python train_ensemble.py --days 365 --output models/ensemble_v1.pkl
    python train_ensemble.py --backtest --days 90
"""

import sys
import os
import json
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')
os.environ['PYTHONUNBUFFERED'] = '1'

from src.database.connection import DatabaseConnection
from src.ml.enhanced_predictor import EnhancedFeatureEngineer, EnsembleTrainer, ProbabilityCalibrator


# Feature columns for the model
BASE_FEATURE_COLS = [
    'current_rating', 'rating_change', 'career_starts', 'career_wins', 'career_win_rate',
    'career_place_rate', 'distance_win_rate', 'distance_place_rate', 'track_win_rate',
    'recent_avg_rank', 'recent_win_rate', 'days_since_last',
    'jockey_win_rate', 'jockey_place_rate', 'trainer_win_rate', 'trainer_place_rate',
    'horse_jockey_win_rate', 'horse_trainer_win_rate',
    'draw', 'draw_advantage', 'win_odds',
    'age', 'season_prize'
]

ODDS_FEATURE_COLS = [
    'odds_drift', 'odds_volatility', 'market_confidence', 'odds_trend', 'odds_compression'
]

PACE_FEATURE_COLS = [
    'early_pace', 'closing_ability', 'pace_figure', 'pace_consistency',
    'is_front_runner', 'is_closer', 'is_stalker'
]

CONDITION_FEATURE_COLS = [
    'wet_win_rate', 'dry_win_rate', 'condition_advantage', 'condition_match'
]

CLASS_FEATURE_COLS = [
    'same_class_win_rate', 'class_rating_trend', 'class_transition', 'class_stability'
]

ALL_FEATURE_COLS = BASE_FEATURE_COLS + ODDS_FEATURE_COLS + PACE_FEATURE_COLS + CONDITION_FEATURE_COLS + CLASS_FEATURE_COLS


def extract_training_data(engineer: EnhancedFeatureEngineer, days: int = 365) -> pd.DataFrame:
    """Extract training data from MongoDB"""
    print(f"[train] Extracting training data from last {days} days...")
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # Get all races with results
    races = list(engineer.db.db['races'].find({
        'race_date': {'$gte': cutoff_date.strftime('%Y-%m-%d')}
    }).sort('race_date', 1))
    
    print(f"[train] Found {len(races)} races")
    
    all_samples = []
    
    for race in races:
        race_id = race.get('race_id', '')
        race_date = race.get('race_date', '')
        race_info = {
            'track_condition': race.get('track_condition', ''),
            'race_class': race.get('class', ''),
            'distance': race.get('distance', 0),
            'venue': race.get('venue', '')
        }
        
        results = race.get('results', [])
        if not results:
            continue
        
        for runner in results:
            horse_name = runner.get('horse_name', '')
            horse = engineer.db.db['horses'].find_one({'name': horse_name})
            if not horse:
                continue
            
            horse_id = horse.get('hkjc_horse_id', '')
            position = engineer._parse_position(runner.get('rank') or runner.get('position'))
            
            # Get base features
            horse_feats = engineer.get_horse_features(horse_id, race_date, race_info)
            
            # Get enhanced features (FEAT-014)
            horse_no = runner.get('horse_number', 0)
            odds_feats = engineer.get_odds_based_features(horse_no, race_id)
            pace_feats = engineer.get_pace_features(horse_id)
            condition_feats = engineer.get_track_condition_features(horse_id, race_info['track_condition'])
            class_feats = engineer.get_class_level_features(horse_id, race_info['race_class'], 
                                                           horse_feats.get('current_rating', 0))
            
            # Combine all features
            sample = {
                'race_id': race_id,
                'horse_id': horse_id,
                'horse_name': horse_name,
                'position': position,
                'won': 1 if position == 1 else 0,
                'top4': 1 if 0 < position <= 4 else 0,
            }
            
            # Add base features
            for col in BASE_FEATURE_COLS:
                sample[col] = horse_feats.get(col, 0)
            
            # Add enhanced features
            for col in ODDS_FEATURE_COLS:
                sample[col] = odds_feats.get(col, 0)
            for col in PACE_FEATURE_COLS:
                sample[col] = pace_feats.get(col, 0)
            for col in CONDITION_FEATURE_COLS:
                sample[col] = condition_feats.get(col, 0)
            for col in CLASS_FEATURE_COLS:
                sample[col] = class_feats.get(col, 0)
            
            all_samples.append(sample)
    
    df = pd.DataFrame(all_samples)
    print(f"[train] Extracted {len(df)} samples, {df['won'].sum()} wins, {df['top4'].sum()} top-4")
    
    return df


def train_and_evaluate(df: pd.DataFrame, output_path: str = None):
    """Train ensemble and evaluate"""
    print("\n[train] Training ensemble model...")
    
    # Prepare features
    feature_cols = [c for c in ALL_FEATURE_COLS if c in df.columns]
    
    X = df[feature_cols].fillna(0).values
    y_top4 = df['top4'].values
    y_win = df['won'].values
    
    # Time-based split (last 20% for validation)
    split_idx = int(len(df) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train_win, y_val_win = y_win[:split_idx], y_win[split_idx:]
    y_train_top4, y_val_top4 = y_top4[:split_idx], y_top4[split_idx:]
    
    print(f"[train] Training: {len(X_train)}, Validation: {len(X_val)}")
    
    # Train Win model
    print("\n[train] Training WIN model...")
    ensemble_win = EnsembleTrainer()
    ensemble_win.train(X_train, y_train_win, X_val, y_val_win)
    
    # Evaluate
    win_proba = ensemble_win.predict_proba(X_val)
    win_uncertainty = ensemble_win.get_uncertainty(X_val)
    
    # Calculate accuracy (top-4)
    win_predictions = ensemble_win.predict(X_val)
    top4_accuracy = np.mean((win_proba >= 0.25) == (y_val_top4 == 1))
    print(f"[train] Win Model - Top-4 Accuracy: {top4_accuracy:.1%}")
    
    # Train Top-4 model
    print("\n[train] Training TOP-4 model...")
    ensemble_top4 = EnsembleTrainer()
    ensemble_top4.train(X_train, y_train_top4, X_val, y_val_top4)
    
    top4_proba = ensemble_top4.predict_proba(X_val)
    top4_predictions = ensemble_top4.predict(X_val)
    
    # Accuracy
    correct = 0
    for i, prob in enumerate(top4_proba):
        top4_pred_indices = np.argsort(prob)[-4:]
        if y_val_top4[i] == 1 and i in top4_pred_indices:
            correct += 1
        elif y_val_top4[i] == 0 and i not in top4_pred_indices:
            correct += 1
    
    top4_accuracy = correct / len(y_val_top4)
    print(f"[train] Top-4 Model - Accuracy: {top4_accuracy:.1%}")
    
    # Average uncertainty
    avg_uncertainty = np.mean(win_uncertainty)
    print(f"[train] Average prediction uncertainty: {avg_uncertainty:.4f}")
    
    # Save models
    if output_path:
        win_path = output_path.replace('.pkl', '_win.pkl')
        top4_path = output_path.replace('.pkl', '_top4.pkl')
        
        ensemble_win.save(os.path.basename(win_path).replace('.pkl', ''))
        ensemble_top4.save(os.path.basename(top4_path).replace('.pkl', ''))
        
        # Save feature columns
        config = {
            'feature_cols': feature_cols,
            'win_model': win_path,
            'top4_model': top4_path,
            'trained_at': datetime.now().isoformat(),
            'n_samples': len(df),
            'top4_accuracy': float(top4_accuracy),
            'avg_uncertainty': float(avg_uncertainty)
        }
        
        config_path = output_path.replace('.pkl', '_config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"\n[train] Models saved:")
        print(f"  - Win model: {win_path}")
        print(f"  - Top-4 model: {top4_path}")
        print(f"  - Config: {config_path}")
    
    return {
        'win_model': ensemble_win,
        'top4_model': ensemble_top4,
        'top4_accuracy': top4_accuracy,
        'avg_uncertainty': avg_uncertainty
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train FEAT-014 Ensemble Model')
    parser.add_argument('--days', type=int, default=365, help='Days of historical data')
    parser.add_argument('--output', type=str, default='models/ensemble_v1.pkl', help='Output path')
    parser.add_argument('--backtest', action='store_true', help='Run backtest only')
    args = parser.parse_args()
    
    # Connect to database
    db = DatabaseConnection()
    db.connect()
    
    # Initialize feature engineer
    engineer = EnhancedFeatureEngineer(db)
    
    # Extract training data
    df = extract_training_data(engineer, days=args.days)
    
    if len(df) < 100:
        print("[train] Not enough training data!")
        sys.exit(1)
    
    # Train
    if not args.backtest:
        results = train_and_evaluate(df, args.output)
        print(f"\n[train] Training complete!")
        print(f"Top-4 Accuracy: {results['top4_accuracy']:.1%}")
