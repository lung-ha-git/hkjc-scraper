#!/usr/bin/env python3
"""
Optimized ML Model Training with More Features
Pre-loads all data for fast training
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score, classification_report
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

from src.database.connection import DatabaseConnection


def load_all_data():
    """Pre-load all data for fast feature building"""
    print("Loading data...")
    
    db = DatabaseConnection()
    db.connect()
    
    # Load races
    races = list(db.db['races'].find({
        'race_date': {'$gte': '2025/01/01', '$lte': '2026/03/01'}
    }))
    print(f"  Races: {len(races)}")
    
    # Load all horses into dict (keyed by name)
    horses = {}
    for h in db.db['horses'].find({}):
        name = h.get('name', '')
        if name:
            horses[name] = h
        # Also index by hkjc_horse_id
        hid = h.get('hkjc_horse_id')
        if hid:
            horses[hid] = h
    print(f"  Horses: {len(horses)}")
    
    # Load all jockeys into dict
    jockeys = {}
    for j in db.db['jockeys'].find({}):
        name = j.get('name', '')
        if name:
            jockeys[name] = j
    print(f"  Jockeys: {len(jockeys)}")
    
    # Load all trainers into dict
    trainers = {}
    for t in db.db['trainers'].find({}):
        name = t.get('name', '')
        if name:
            trainers[name] = t
    print(f"  Trainers: {len(trainers)}")
    
    # Load horse distance stats
    distance_stats = {}
    for ds in db.db['horse_distance_stats'].find({}):
        hid = ds.get('hkjc_horse_id')
        if hid:
            distance_stats[hid] = ds
    print(f"  Distance stats: {len(distance_stats)}")
    
    return {
        'races': races,
        'horses': horses,
        'jockeys': jockeys,
        'trainers': trainers,
        'distance_stats': distance_stats
    }


def build_features(data):
    """Build features from loaded data"""
    print("\nBuilding features...")
    
    races = data['races']
    horses = data['horses']
    jockeys = data['jockeys']
    trainers = data['trainers']
    distance_stats = data['distance_stats']
    
    samples = []
    
    for race in races:
        results = race.get('results', [])
        race_date = race.get('race_date', '')
        race_distance = race.get('distance', 0) or 0
        race_venue = race.get('venue', '')
        
        for r in results:
            # Parse rank
            rank = r.get('rank', 0)
            try:
                rank = int(rank) if rank else 0
            except:
                rank = 0
            
            if rank == 0:
                continue
            
            horse_name = r.get('horse_name', '')
            jockey_name = r.get('jockey', '')
            trainer_name = r.get('trainer', '')
            
            # Find horse
            horse = horses.get(horse_name)
            if not horse:
                # Try partial match
                for hn, h in horses.items():
                    if horse_name and hn and horse_name in hn:
                        horse = h
                        break
            
            # Get horse features
            if horse:
                hid = horse.get('hkjc_horse_id', '')
                current_rating = horse.get('current_rating', 0) or 0
                career_wins = horse.get('career_wins', 0) or 0
                career_starts = horse.get('career_starts', 0) or 0
                career_seconds = horse.get('career_seconds', 0) or 0
                career_thirds = horse.get('career_thirds', 0) or 0
                season_prize = horse.get('season_prize', 0) or 0
                
                # Distance stats
                ds = distance_stats.get(hid, {})
                dp = ds.get('distance_performance', [])
                
                dist_wins = 0
                dist_runs = 0
                dist_str = f"{race_distance}米"
                for d in dp:
                    if dist_str in d.get('distance', ''):
                        dist_runs = d.get('total_runs', 0) or 0
                        dist_wins = d.get('first', 0) or 0
                        break
            else:
                current_rating = 0
                career_wins = 0
                career_starts = 0
                career_seconds = 0
                career_thirds = 0
                season_prize = 0
                dist_wins = 0
                dist_runs = 0
            
            # Get jockey features
            jockey = jockeys.get(jockey_name)
            if jockey:
                j_wins = jockey.get('wins', 0) or 0
                j_rides = jockey.get('total_rides', 0) or 0
                j_win_rate = j_wins / j_rides if j_rides > 0 else 0
            else:
                j_wins = 0
                j_rides = 0
                j_win_rate = 0
            
            # Get trainer features
            trainer = trainers.get(trainer_name)
            if trainer:
                t_wins = trainer.get('wins', 0) or 0
                t_races = trainer.get('total_races', 0) or 0
                t_win_rate = t_wins / t_races if t_races > 0 else 0
            else:
                t_wins = 0
                t_races = 0
                t_win_rate = 0
            
            # Build sample
            sample = {
                # Race features
                'draw': r.get('draw', 0) or 0,
                'win_odds': r.get('win_odds', 0) or 0,
                'distance': race_distance,
                'venue': 1 if race_venue == 'HV' else 0,  # 1 = Happy Valley, 0 = Sha Tin
                
                # Horse features
                'current_rating': current_rating,
                'career_starts': career_starts,
                'career_wins': career_wins,
                'career_seconds': career_seconds,
                'career_thirds': career_thirds,
                'career_win_rate': career_wins / career_starts if career_starts > 0 else 0,
                'career_place_rate': (career_wins + career_seconds + career_thirds) / career_starts if career_starts > 0 else 0,
                'season_prize': season_prize,
                'dist_wins': dist_wins,
                'dist_runs': dist_runs,
                'dist_win_rate': dist_wins / dist_runs if dist_runs > 0 else 0,
                
                # Jockey features
                'jockey_wins': j_wins,
                'jockey_rides': j_rides,
                'jockey_win_rate': j_win_rate,
                
                # Trainer features
                'trainer_wins': t_wins,
                'trainer_races': t_races,
                'trainer_win_rate': t_win_rate,
                
                # Labels
                'rank': rank,
                'place': 1 if rank <= 3 else 0,
                'win': 1 if rank == 1 else 0,
            }
            
            samples.append(sample)
    
    df = pd.DataFrame(samples)
    print(f"  Total samples: {len(df)}")
    print(f"  Places: {df['place'].sum()}, Wins: {df['win'].sum()}")
    
    return df


def train_models(df):
    """Train models with the dataset"""
    print("\n" + "="*60)
    print("Training Models")
    print("="*60)
    
    # Define features
    feature_cols = [
        # Race
        'draw', 'win_odds', 'distance', 'venue',
        # Horse
        'current_rating', 'career_starts', 'career_wins', 'career_seconds', 'career_thirds',
        'career_win_rate', 'career_place_rate', 'season_prize',
        'dist_wins', 'dist_runs', 'dist_win_rate',
        # Jockey
        'jockey_wins', 'jockey_rides', 'jockey_win_rate',
        # Trainer
        'trainer_wins', 'trainer_races', 'trainer_win_rate',
    ]
    
    X = df[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
    
    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Split for place prediction
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, df['place'], test_size=0.2, random_state=42, stratify=df['place']
    )
    
    print(f"\nTrain: {len(X_train)}, Test: {len(X_test)}")
    print(f"Features: {len(feature_cols)}")
    
    # Train Gradient Boosting
    print("\n--- Training Gradient Boosting (Place) ---")
    gb_model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42
    )
    gb_model.fit(X_train, y_train)
    
    y_pred = gb_model.predict(X_test)
    y_prob = gb_model.predict_proba(X_test)[:, 1]
    
    print(f"\n=== Place Prediction Results ===")
    print(f"Accuracy:  {accuracy_score(y_test, y_pred):.3f}")
    print(f"Precision: {precision_score(y_test, y_pred):.3f}")
    print(f"Recall:    {recall_score(y_test, y_pred):.3f}")
    print(f"AUC:       {roc_auc_score(y_test, y_prob):.3f}")
    
    # Feature importance
    print(f"\n=== Feature Importance (Top 10) ===")
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': gb_model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    for _, row in importance.head(10).iterrows():
        print(f"  {row['feature']:25s}: {row['importance']:.4f}")
    
    # Train Win model
    print("\n--- Training Gradient Boosting (Win) ---")
    X_train_w, X_test_w, y_train_w, y_test_w = train_test_split(
        X_scaled, df['win'], test_size=0.2, random_state=42, stratify=df['win']
    )
    
    gb_win = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42
    )
    gb_win.fit(X_train_w, y_train_w)
    
    y_pred_w = gb_win.predict(X_test_w)
    y_prob_w = gb_win.predict_proba(X_test_w)[:, 1]
    
    print(f"\n=== Win Prediction Results ===")
    print(f"Accuracy:  {accuracy_score(y_test_w, y_pred_w):.3f}")
    print(f"Precision: {precision_score(y_test_w, y_pred_w):.3f}")
    print(f"Recall:    {recall_score(y_test_w, y_pred_w):.3f}")
    print(f"AUC:       {roc_auc_score(y_test_w, y_prob_w):.3f}")
    
    return {
        'place_model': gb_model,
        'win_model': gb_win,
        'feature_cols': feature_cols,
        'scaler': scaler,
        'feature_importance': importance
    }


def main():
    start = datetime.now()
    
    # Load data
    data = load_all_data()
    
    # Build features
    df = build_features(data)
    
    # Train models
    results = train_models(df)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"Training complete in {elapsed:.1f} seconds")
    print("="*60)
    
    # Save dataset
    df.to_csv('/Users/fatlung/.openclaw/workspace-main/hkjc_project/data/training_data_2026.csv', index=False)
    print(f"\nSaved dataset to data/training_data_2026.csv")


if __name__ == "__main__":
    main()
