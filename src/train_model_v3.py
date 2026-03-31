#!/usr/bin/env python3
"""
HKJC Racing ML Model - Optimized with 25 Features
Train models without win_odds (for pre-race predictions)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from src.database.connection import DatabaseConnection


def load_data():
    """Load all data from MongoDB"""
    db = DatabaseConnection()
    db.connect()
    
    races = list(db.db['races'].find({}).sort('race_date', 1))
    horses = {h.get('name', ''): h for h in db.db['horses'].find({})}
    horses.update({h.get('hkjc_horse_id'): h for h in db.db['horses'].find({})})
    jockeys = {j.get('name', ''): j for j in db.db['jockeys'].find({})}
    trainers = {t.get('name', ''): t for t in db.db['trainers'].find({})}
    distance_stats = {ds.get('hkjc_horse_id'): ds for ds in db.db['horse_distance_stats'].find({})}
    
    # Race history for recent form
    race_history = {}
    for rh in db.db['horse_race_history'].find({}):
        hid = rh.get('hkjc_horse_id')
        if hid:
            if hid not in race_history:
                race_history[hid] = []
            try:
                rank = int(rh.get('position', 0)) if rh.get('position') else 0
            except:
                rank = 0
            race_history[hid].append({'date': rh.get('date', ''), 'rank': rank, 'distance': rh.get('distance', 0)})
    
    for hid in race_history:
        race_history[hid].sort(key=lambda x: x.get('date', ''), reverse=True)
    
    return {
        'races': races,
        'horses': horses,
        'jockeys': jockeys,
        'trainers': trainers,
        'distance_stats': distance_stats,
        'race_history': race_history,
    }


def build_features(data):
    """Build feature matrix from raw data"""
    races = data['races']
    horses = data['horses']
    jockeys = data['jockeys']
    trainers = data['trainers']
    distance_stats = data['distance_stats']
    race_history = data['race_history']
    
    samples = []
    
    for race in races:
        race_dist = race.get('distance', 0) or 0
        race_venue = race.get('venue', '')
        
        for r in race.get('results', []):
            try:
                rank = int(r.get('rank', 0)) if r.get('rank') else 0
            except:
                rank = 0
            if rank == 0:
                continue
            
            horse_name = r.get('horse_name', '')
            jockey_name = r.get('jockey', '')
            trainer_name = r.get('trainer', '')
            
            horse = horses.get(horse_name)
            hid = horse.get('hkjc_horse_id', '') if horse else ''
            
            # Horse basic
            current_rating = int(horse.get('current_rating', 0) or 0) if horse else 0
            career_starts = int(horse.get('career_starts', 0) or 0) if horse else 0
            career_wins = int(horse.get('career_wins', 0) or 0) if horse else 0
            career_seconds = int(horse.get('career_seconds', 0) or 0) if horse else 0
            career_thirds = int(horse.get('career_thirds', 0) or 0) if horse else 0
            season_prize = int(horse.get('season_prize', 0) or 0) if horse else 0
            
            # Distance performance
            ds = distance_stats.get(hid, {})
            dp = ds.get('distance_performance', [])
            
            dist_wins = dist_runs = dist_win_rate = 0
            dist_str = f'{race_dist}米'
            for d in dp:
                if dist_str in d.get('distance', ''):
                    dist_runs = int(d.get('total_runs', 0) or 0)
                    dist_wins = int(d.get('first', 0) or 0)
                    dist_win_rate = dist_wins / dist_runs if dist_runs > 0 else 0
                    break
            
            # Track performance
            tp = ds.get('track_performance', [])
            track_wins = track_runs = track_win_rate = 0
            for t in tp:
                if '草地' in t.get('surface', ''):
                    track_runs = int(t.get('starts', 0) or 0)
                    track_wins = int(t.get('win', 0) or 0)
                    track_win_rate = track_wins / track_runs if track_runs > 0 else 0
                    break
            
            # Recent form
            recent_ranks = []
            recent_dist_ranks = []
            if hid in race_history:
                for rh in race_history[hid][:10]:
                    r_rank = rh.get('rank', 0)
                    if r_rank:
                        recent_ranks.append(r_rank)
                    if rh.get('distance') == race_dist:
                        recent_dist_ranks.append(r_rank)
            
            recent_avg_rank = sum(recent_ranks) / len(recent_ranks) if recent_ranks else 0
            recent_wins = sum(1 for r in recent_ranks if r == 1)
            recent_places = sum(1 for r in recent_ranks if 0 < r <= 3)
            dist_recent_wins = sum(1 for r in recent_dist_ranks if r == 1)
            dist_recent_avg = sum(recent_dist_ranks) / len(recent_dist_ranks) if recent_dist_ranks else 0
            
            # Jockey
            j = jockeys.get(jockey_name)
            j_wins = int(j.get('wins', 0) or 0) if j else 0
            j_rides = int(j.get('total_rides', 0) or 0) if j else 0
            j_win_rate = j_wins / j_rides if j_rides > 0 else 0
            
            # Trainer
            t = trainers.get(trainer_name)
            t_wins = int(t.get('wins', 0) or 0) if t else 0
            t_horses = int(t.get('total_horses', 0) or 0) if t else 0
            t_win_rate = t_wins / t_horses if t_horses > 0 else 0
            
            # Career place rate
            career_place = career_wins + career_seconds + career_thirds
            career_place_rate = career_place / career_starts if career_starts > 0 else 0
            
            samples.append({
                'draw': int(r.get('draw', 0) or 0),
                'distance': race_dist,
                'venue': 1 if race_venue == 'HV' else 0,
                'current_rating': current_rating,
                'career_starts': career_starts,
                'career_wins': career_wins,
                'career_place_rate': career_place_rate,
                'season_prize': season_prize,
                'dist_wins': dist_wins,
                'dist_runs': dist_runs,
                'dist_win_rate': dist_win_rate,
                'track_wins': track_wins,
                'track_runs': track_runs,
                'track_win_rate': track_win_rate,
                'recent_avg_rank': recent_avg_rank,
                'recent_wins': recent_wins,
                'recent_places': recent_places,
                'dist_recent_wins': dist_recent_wins,
                'dist_recent_avg': dist_recent_avg,
                'jockey_wins': j_wins,
                'jockey_rides': j_rides,
                'jockey_win_rate': j_win_rate,
                'trainer_wins': t_wins,
                'trainer_horses': t_horses,
                'trainer_win_rate': t_win_rate,
                'place': 1 if rank <= 3 else 0,
                'win': 1 if rank == 1 else 0,
            })
    
    return pd.DataFrame(samples)


def train_models(df):
    """Train and evaluate models"""
    feature_cols = [
        'draw', 'distance', 'venue',
        'current_rating', 'career_starts', 'career_wins', 'career_place_rate', 'season_prize',
        'dist_wins', 'dist_runs', 'dist_win_rate',
        'track_wins', 'track_runs', 'track_win_rate',
        'recent_avg_rank', 'recent_wins', 'recent_places',
        'dist_recent_wins', 'dist_recent_avg',
        'jockey_wins', 'jockey_rides', 'jockey_win_rate',
        'trainer_wins', 'trainer_horses', 'trainer_win_rate',
    ]
    
    X = df[feature_cols].fillna(0).replace([float('inf'), float('-inf')], 0)
    X_scaled = StandardScaler().fit_transform(X)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, df['place'], test_size=0.2, random_state=42, stratify=df['place']
    )
    
    # Place model
    gb = GradientBoostingClassifier(
        n_estimators=200, max_depth=5, learning_rate=0.08, 
        min_samples_leaf=10, random_state=42
    )
    gb.fit(X_train, y_train)
    y_prob = gb.predict_proba(X_test)[:, 1]
    
    results = {
        'accuracy': accuracy_score(y_test, gb.predict(X_test)),
        'auc': roc_auc_score(y_test, y_prob),
        'precision': precision_score(y_test, gb.predict(X_test)),
        'recall': recall_score(y_test, gb.predict(X_test)),
        'feature_importance': dict(zip(feature_cols, gb.feature_importances_)),
    }
    
    return results


def main():
    start = datetime.now()
    
    print("Loading data...")
    data = load_data()
    print(f"  Races: {len(data['races'])}")
    
    print("\nBuilding features...")
    df = build_features(data)
    print(f"  Samples: {len(df)}")
    print(f"  Places: {df['place'].sum()}")
    
    print("\nTraining models...")
    results = train_models(df)
    
    print(f"\n{'='*60}")
    print("RESULTS (25 Features, NO win_odds)")
    print("="*60)
    print(f"Accuracy:  {results['accuracy']:.3f}")
    print(f"Precision: {results['precision']:.3f}")
    print(f"Recall:    {results['recall']:.3f}")
    print(f"AUC:       {results['auc']:.3f}")
    
    print(f"\nTop 10 Features:")
    sorted_features = sorted(results['feature_importance'].items(), key=lambda x: -x[1])
    for f, i in sorted_features[:10]:
        print(f"  {f:25s}: {i:.4f}")
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\nCompleted in {elapsed:.1f} seconds")
    
    # Save dataset
    df.to_csv('data/training_data_v2.csv', index=False)
    print("Saved dataset to data/training_data_v2.csv")


if __name__ == "__main__":
    main()
