#!/usr/bin/env python3
"""
FEAT-014: Enhanced Prediction Script

Usage:
    python predict_enhanced.py --date 2026-03-25 --race 1 --venue HV
    python predict_enhanced.py --race-id 2026-03-25_HV_R1
"""

import sys
import os
import argparse
import json
import numpy as np

sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')
os.environ['PYTHONUNBUFFERED'] = '1'

from src.database.connection import DatabaseConnection
from src.ml.enhanced_predictor import EnhancedFeatureEngineer, EnsembleTrainer


def load_models(model_dir='models'):
    """Load trained ensemble models"""
    models = {}
    
    # Try to load win model
    try:
        ensemble_win = EnsembleTrainer(model_dir)
        ensemble_win.load('ensemble_v1_win')
        models['win'] = ensemble_win
        print("[predict] Loaded WIN model")
    except Exception as e:
        print(f"[predict] No WIN model: {e}")
    
    # Try to load top4 model
    try:
        ensemble_top4 = EnsembleTrainer(model_dir)
        ensemble_top4.load('ensemble_v1_top4')
        models['top4'] = ensemble_top4
        print("[predict] Loaded TOP-4 model")
    except Exception as e:
        print(f"[predict] No TOP-4 model: {e}")
    
    # Load config
    try:
        with open(os.path.join(model_dir, 'ensemble_v1_config.json'), 'r') as f:
            config = json.load(f)
            print(f"[predict] Model config: {config.get('n_samples', 0)} samples, "
                  f"accuracy: {config.get('top4_accuracy', 'N/A')}")
            return models, config.get('feature_cols', [])
    except Exception as e:
        print(f"[predict] No config found: {e}")
    
    return models, []


def get_confidence_level(uncertainty: float, model_agreement: float) -> str:
    """Determine confidence level based on uncertainty and model agreement"""
    if uncertainty < 0.05 and model_agreement > 0.8:
        return "HIGH"
    elif uncertainty < 0.1 and model_agreement > 0.6:
        return "MEDIUM"
    else:
        return "LOW"


def predict_race(db: DatabaseConnection, race_id: str, models: dict = None, feature_cols: list = None):
    """Make predictions for a race"""
    
    # Initialize feature engineer
    engineer = EnhancedFeatureEngineer(db)
    
    # Build enhanced features
    race_features = engineer.build_enhanced_race_features(race_id, include_odds=True)
    
    if not race_features or not race_features.get('horses'):
        print(f"[predict] No features for race {race_id}")
        return None
    
    horses = race_features['horses']
    race_info = race_features.get('race_info', {})
    
    print(f"\n{'='*60}")
    print(f"Race: {race_id}")
    print(f"Date: {race_info.get('race_date', 'N/A')} | Venue: {race_info.get('venue', 'N/A')}")
    print(f"Distance: {race_info.get('distance', 'N/A')} | Class: {race_info.get('race_class', 'N/A')}")
    print(f"Track: {race_info.get('track_condition', 'N/A')}")
    print(f"{'='*60}")
    
    # Prepare features for prediction - ONLY use numeric columns from config
    if feature_cols is None:
        from train_ensemble import ALL_FEATURE_COLS
        feature_cols = ALL_FEATURE_COLS
    
    X = []
    valid_horses = []
    
    for h in horses:
        features = []
        for col in feature_cols:
            val = 0
            # Check nested feature dicts
            if col in h:
                val = h[col]
            elif 'odds_features' in h and col in h['odds_features']:
                val = h['odds_features'][col]
            elif 'pace_features' in h and col in h['pace_features']:
                val = h['pace_features'][col]
            elif 'condition_features' in h and col in h['condition_features']:
                val = h['condition_features'][col]
            elif 'class_features' in h and col in h['class_features']:
                val = h['class_features'][col]
            
            # Convert to numeric
            if isinstance(val, (int, float)):
                features.append(float(val))
            elif val is None:
                features.append(0.0)
            elif isinstance(val, str):
                # Skip string values - they shouldn't be in feature_cols
                features.append(0.0)
            else:
                features.append(float(val) if val else 0.0)
        
        X.append(features)
        valid_horses.append(h)
    
    X = np.array(X, dtype=np.float32)
    
    # Make predictions
    results = []
    
    if 'top4' in models:
        model = models['top4']
        
        # Ensure X is 2D
        if len(X.shape) == 1:
            X = X.reshape(1, -1)
        
        proba = model.predict_proba(X)
        
        # Ensure proba is 2D
        if len(proba.shape) == 1:
            proba = proba.reshape(-1, 1)
        
        uncertainty = model.get_uncertainty(X)
        
        # Get model agreement
        all_proba = np.column_stack([m.predict_proba(X)[:, 1] if len(m.predict_proba(X).shape) > 1 else m.predict_proba(X).reshape(-1, 1) for m in models.values()])
        model_agreement = 1 - np.std(all_proba, axis=1)
        
        for i, h in enumerate(valid_horses):
            conf = get_confidence_level(uncertainty[i], model_agreement[i])
            
            result = {
                'horse_no': h.get('horse_number', 0),
                'horse_name': h.get('horse_name', ''),
                'probability': float(proba[i]),
                'ensemble_std': float(uncertainty[i]),
                'model_agreement': float(model_agreement[i]),
                'confidence': conf,
                'win_odds': h.get('win_odds', 0),
                'rating': h.get('current_rating', 0),
                'jockey': h.get('jockey_name', ''),
                'draw': h.get('draw', 0),
            }
            results.append(result)
    else:
        # Fallback to basic probability using odds
        for h in valid_horses:
            win_odds = h.get('win_odds', 10)
            prob = 1 / win_odds if win_odds > 0 else 0.1
            
            result = {
                'horse_no': h.get('horse_number', 0),
                'horse_name': h.get('horse_name', ''),
                'probability': float(prob),
                'ensemble_std': 0.1,
                'model_agreement': 0.5,
                'confidence': 'LOW',
                'win_odds': win_odds,
                'rating': h.get('current_rating', 0),
                'jockey': h.get('jockey_name', ''),
                'draw': h.get('draw', 0),
            }
            results.append(result)
    
    # Sort by probability
    results.sort(key=lambda x: x['probability'], reverse=True)
    
    # Display results
    print(f"\n{'No':<4} {'Horse':<15} {'Odds':<8} {'Rating':<7} {'Prob':<7} {'Conf':<8} {'STD':<6}")
    print('-' * 70)
    
    for r in results:
        conf_emoji = '🟢' if r['confidence'] == 'HIGH' else ('🟡' if r['confidence'] == 'MEDIUM' else '🔴')
        print(f"{r['horse_no']:<4} {r['horse_name'][:15]:<15} {r['win_odds']:<8.1f} "
              f"{r['rating']:<7} {r['probability']:<7.3f} {conf_emoji} {r['confidence']:<6} {r['ensemble_std']:.3f}")
    
    # Top-4 selection
    print(f"\n📊 Top-4 Selection:")
    top4 = results[:4]
    for i, r in enumerate(top4, 1):
        print(f"  {i}. {r['horse_name']} (No.{r['horse_no']}) - {r['probability']:.1%}")
    
    # Calculate confidence index (similar to existing webapp)
    top4_raw_score_sum = sum(r['probability'] for r in top4)
    confidence_index = max(0, min(100, 100 - top4_raw_score_sum * 100))
    
    print(f"\n🎯 Confidence Index: {confidence_index:.0f}")
    
    return {
        'race_id': race_id,
        'race_info': race_info,
        'predictions': results,
        'top4': top4,
        'confidence_index': confidence_index
    }


def find_race_id(db: DatabaseConnection, date: str, venue: str, race_no: int) -> str:
    """Find race ID from date, venue, and race number"""
    race = db.db['races'].find_one({
        'race_date': date,
        'venue': venue.upper(),
        'race_no': race_no
    })
    
    if race:
        return race.get('race_id', '')
    
    # Try alternate format
    race = db.db['races'].find_one({
        'race_date': {'$regex': date.replace('-', '/')},
        'venue': venue.upper(),
        'race_no': race_no
    })
    
    if race:
        return race.get('race_id', '')
    
    return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='FEAT-014 Enhanced Predictions')
    parser.add_argument('--date', type=str, help='Race date (YYYY-MM-DD)')
    parser.add_argument('--venue', type=str, help='Venue (HV/ST)')
    parser.add_argument('--race', type=int, help='Race number')
    parser.add_argument('--race-id', type=str, help='Race ID directly')
    parser.add_argument('--model-dir', type=str, default='models', help='Model directory')
    args = parser.parse_args()
    
    # Connect to database
    db = DatabaseConnection()
    db.connect()
    
    # Load models
    models, feature_cols = load_models(args.model_dir)
    
    # Find race
    if args.race_id:
        race_id = args.race_id
    elif args.date and args.venue and args.race:
        race_id = find_race_id(db, args.date, args.venue, args.race)
        if not race_id:
            print(f"[predict] Race not found: {args.date} {args.venue} R{args.race}")
            sys.exit(1)
    else:
        print("[predict] Please provide --race-id or --date/--venue/--race")
        sys.exit(1)
    
    # Predict
    result = predict_race(db, race_id, models, feature_cols)
    
    if result:
        print(f"\n✅ Prediction complete for {race_id}")
