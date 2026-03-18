#!/usr/bin/env python3
"""
XGBoost Model Prediction Script
"""
import sys
import os
import json
import pickle

sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')
os.environ['PYTHONUNBUFFERED'] = '1'

from src.database.connection import DatabaseConnection
from collections import defaultdict


def load_model():
    """Load XGBoost model"""
    with open('/Users/fatlung/.openclaw/workspace-main/hkjc_project/xgb_model.pkl', 'rb') as f:
        data = pickle.load(f)
    return data['model'], data['features']


def load_data():
    """Load data from MongoDB"""
    db = DatabaseConnection()
    db.connect()
    
    races = list(db.db['races'].find({}).sort('race_date', 1))
    
    horses = {h.get('name', ''): h for h in db.db['horses'].find({})}
    horses.update({h.get('hkjc_horse_id'): h for h in db.db['horses'].find({})})
    jockeys = {j.get('name', ''): j for j in db.db['jockeys'].find({})}
    trainers = {t.get('name', ''): t for t in db.db['trainers'].find({})}
    distance_stats = {ds.get('hkjc_horse_id'): ds for ds in db.db['horse_distance_stats'].find({})}
    
    # Build combo stats
    jt_wins, jt_races = defaultdict(int), defaultdict(int)
    hj_wins, hj_races = defaultdict(int), defaultdict(int)
    
    for race in races:
        for r in race.get('results', []):
            jockey, trainer, horse_name = r.get('jockey', ''), r.get('trainer', ''), r.get('horse_name', '')
            try: rank = int(r.get('rank', 0)) if r.get('rank') else 0
            except: rank = 0
            if jockey and trainer:
                jt_races[(jockey, trainer)] += 1
                if rank == 1: jt_wins[(jockey, trainer)] += 1
            if horse_name and jockey:
                hj_races[(horse_name, jockey)] += 1
                if rank == 1: hj_wins[(horse_name, jockey)] += 1
    
    return db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races


def build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races):
    """Build features for race entries"""
    results = []
    
    race_ratings = [horses.get(e.get('horse_name', ''), {}).get('current_rating', 0) or 0 for e in entries]
    race_avg = sum(race_ratings) / len(race_ratings) if race_ratings else 0
    
    for entry in entries:
        horse_name = entry.get('horse_name', '')
        jockey = entry.get('jockey_name', '')
        trainer = entry.get('trainer_name', '')
        draw = entry.get('draw', 0) or 0
        
        horse = horses.get(horse_name, {})
        hid = horse.get('hkjc_horse_id', '') if horse else ''
        
        current_rating = int(horse.get('current_rating', 0) or 0) if horse else 0
        career_starts = int(horse.get('career_starts', 0) or 0) if horse else 0
        career_wins = int(horse.get('career_wins', 0) or 0) if horse else 0
        career_seconds = int(horse.get('career_seconds', 0) or 0) if horse else 0
        career_thirds = int(horse.get('career_thirds', 0) or 0) if horse else 0
        
        career_place = career_wins + career_seconds + career_thirds
        career_place_rate = career_place / career_starts if career_starts > 0 else 0
        
        # Distance performance
        ds = distance_stats.get(hid, {})
        dp = ds.get('distance_performance', [])
        
        dist_wins = dist_runs = dist_win_rate = 0
        dist_str = f'{distance}米'
        for d in dp:
            if dist_str in d.get('distance', ''):
                dist_runs = int(d.get('total_runs', 0) or 0)
                dist_wins = int(d.get('first', 0) or 0)
                dist_win_rate = dist_wins / dist_runs if dist_runs > 0 else 0
                break
        
        # Jockey-trainer combo
        jt = (jockey, trainer)
        jt_win_rate = jt_wins.get(jt, 0) / jt_races.get(jt, 1) if jt_races.get(jt, 0) > 0 else 0
        
        # Horse-jockey combo
        hj = (horse_name, jockey)
        hj_win_rate = hj_wins.get(hj, 0) / hj_races.get(hj, 1) if hj_races.get(hj, 0) > 0 else 0
        
        # Jockey
        j = jockeys.get(jockey, {})
        jockey_win_rate = (j.get('wins', 0) or 0) / max(1, (j.get('total_rides', 0) or 0)) if j else 0
        
        # Trainer
        t = trainers.get(trainer, {})
        trainer_win_rate = (t.get('wins', 0) or 0) / max(1, (t.get('total_horses', 0) or 0)) if t else 0
        
        results.append({
            'horse_name': horse_name,
            'jockey': jockey,
            'trainer': trainer,
            'draw': draw,
            'distance': distance,
            'venue': 1 if venue == 'HV' else 0,
            'current_rating': current_rating,
            'relative_rating': current_rating - race_avg,
            'career_starts': career_starts,
            'career_wins': career_wins,
            'career_place_rate': career_place_rate,
            'dist_wins': dist_wins,
            'dist_runs': dist_runs,
            'dist_win_rate': dist_win_rate,
            'jockey_win_rate': jockey_win_rate,
            'trainer_win_rate': trainer_win_rate,
            'jt_win_rate': jt_win_rate,
            'hj_win_rate': hj_win_rate,
            'draw_dist': draw * distance,
            'hj_races': hj_races.get(hj, 0),
        })
    
    return results


def predict_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, model, features):
    """Predict race using XGBoost model"""
    entry_features = build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races)
    
    # Build feature matrix
    import numpy as np
    
    X = []
    for ef in entry_features:
        row = []
        for f in features:
            row.append(ef.get(f, 0))
        X.append(row)
    
    X = np.array(X)
    
    # Predict
    preds = model.predict(X)
    
    # Combine with entry data
    results = []
    for i, ef in enumerate(entry_features):
        results.append({
            'horse_name': ef['horse_name'],
            'jockey': ef['jockey'],
            'trainer': ef['trainer'],
            'draw': ef['draw'],
            'score': float(preds[i]),
        })
    
    # Sort by score (lower is better - predicted rank)
    results.sort(key=lambda x: x['score'])
    for i, r in enumerate(results):
        r['predicted_rank'] = i + 1
    
    return results


if __name__ == '__main__':
    import sys
    
    race_date = sys.argv[1] if len(sys.argv) > 1 else '2026-03-18'
    race_no = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    venue = sys.argv[3] if len(sys.argv) > 3 else 'HV'
    
    print(f'Loading model and data for {race_date} R{race_no} {venue}...')
    
    model, features = load_model()
    db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races = load_data()
    
    # Get racecard entries
    racecard_entries = list(db.db['racecard_entries'].find({
        'race_date': race_date,
        'venue': venue,
        'race_no': race_no
    }))
    
    racecard = db.db['racecards'].find_one({
        'race_date': race_date,
        'venue': venue,
        'race_no': race_no
    })
    
    distance = racecard.get('distance', 1200) if racecard else 1200
    
    predictions = predict_race(racecard_entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, model, features)
    
    print(json.dumps({'predictions': predictions}, ensure_ascii=False))
