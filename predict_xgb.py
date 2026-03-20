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
    
    # Imports must be at function top (Python treats 'from X import Y' as local for entire function)
    from collections import defaultdict
    from datetime import datetime
    
    # Build combo stats
    jt_wins, jt_races = defaultdict(int), defaultdict(int)
    hj_wins, hj_races = defaultdict(int), defaultdict(int)
    hj_places, jt_places = defaultdict(int), defaultdict(int)
    
    for race in races:
        for r in race.get('results', []):
            jockey, trainer, horse_name = r.get('jockey', ''), r.get('trainer', ''), r.get('horse_name', '')
            try: rank = int(r.get('rank', 0)) if r.get('rank') else 0
            except: rank = 0
            if jockey and trainer:
                jt_races[(jockey, trainer)] += 1
                if rank == 1: jt_wins[(jockey, trainer)] += 1
                if rank <= 3: jt_places[(jockey, trainer)] += 1
            if horse_name and jockey:
                hj_races[(horse_name, jockey)] += 1
                if rank == 1: hj_wins[(horse_name, jockey)] += 1
                if rank <= 3: hj_places[(horse_name, jockey)] += 1
    
    # Build horse last race data (for days_rest and weight_change)
    horse_last_race = {}
    for race in races:
        for r in race.get('results', []):
            horse_name = r.get('horse_name', '')
            if not horse_name:
                continue
            race_date_str = race.get('race_date', '')
            try:
                rd = datetime.strptime(race_date_str.replace('/', '-'), '%Y-%m-%d')
            except Exception:
                continue
            if horse_name not in horse_last_race or rd > horse_last_race[horse_name]['date']:
                horse_last_race[horse_name] = {
                    'date': rd,
                    'draw_weight': r.get('draw_weight') or r.get('weight'),
                    'position': r.get('rank') or r.get('position'),
                }
    
    # Build horse early pace score from running_position
    # First position of "1 3 5" pattern = front-runner indicator
    # Lower = more forward, Higher = closer/back
    horse_pace_positions = defaultdict(list)
    for race in races:
        for r in race.get('results', []):
            horse_name = r.get('horse_name', '')
            if not horse_name:
                continue
            running_pos = r.get('running_position', '')
            if not running_pos:
                continue
            try:
                first_pos = int(running_pos.split()[0])
                horse_pace_positions[horse_name].append(first_pos)
            except Exception:
                continue
    
    # Average early pace per horse (lower = front-runner)
    horse_early_pace = {
        h: sum(poses) / len(poses)
        for h, poses in horse_pace_positions.items()
        if poses
    }
    
    return db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, horse_early_pace


def _get_draw_advantage(draw: int, venue: str, distance: int) -> float:
    """
    Calculate draw advantage/disadvantage.
    
    Rules:
    - ST 1000m: outer draw (high draw = 檔位大) = advantage (can avoid being trapped inside)
    - HV all distances: inner draw (low draw = 檔位小) = advantage
    
    Returns:
        Positive = advantage, Negative = disadvantage, 0 = neutral
    """
    if draw is None or draw == 0:
        return 0
    
    if venue == 'HV':
        # Happy Valley: inner draw is always better
        # 1=最內檔(advantage) to 14=最外檔
        return 8 - draw  # draw 1 → +7, draw 8 → 0, draw 14 → -6
    
    if venue == 'ST' and distance == 1000:
        # Sha Tin 1000m: outer draw is better (can get out from inside)
        return draw - 8  # draw 14 → +6, draw 8 → 0, draw 1 → -7
    
    # ST other distances: no strong draw bias in model (default 0)
    return 0


def build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, race_date, horse_early_pace):
    """Build features for race entries"""
    results = []
    
    race_ratings = [horses.get(e.get('horse_name', ''), {}).get('current_rating', 0) or 0 for e in entries]
    race_avg = sum(race_ratings) / len(race_ratings) if race_ratings else 0
    
    for entry in entries:
        horse_name = entry.get('horse_name', '')
        jockey = entry.get('jockey_name', '')
        trainer = entry.get('trainer_name', '')
        draw = entry.get('draw', 0) or 0
        scratch_weight = entry.get('scratch_weight', 0) or 0
        
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
        jt_place_rate = jt_places.get(jt, 0) / jt_races.get(jt, 1) if jt_races.get(jt, 0) > 0 else 0
        
        # Horse-jockey combo
        hj = (horse_name, jockey)
        hj_win_rate = hj_wins.get(hj, 0) / hj_races.get(hj, 1) if hj_races.get(hj, 0) > 0 else 0
        hj_place_rate = hj_places.get(hj, 0) / hj_races.get(hj, 1) if hj_races.get(hj, 0) > 0 else 0
        
        # Jockey
        j = jockeys.get(jockey, {})
        jockey_win_rate = (j.get('wins', 0) or 0) / max(1, (j.get('total_rides', 0) or 0)) if j else 0
        
        # Trainer
        t = trainers.get(trainer, {})
        trainer_win_rate = (t.get('wins', 0) or 0) / max(1, (t.get('total_horses', 0) or 0)) if t else 0
        
        # Days rest (days since last race)
        from datetime import datetime
        try:
            race_dt = datetime.strptime(race_date.replace('/', '-'), '%Y-%m-%d')
        except Exception:
            race_dt = datetime.now()
        last = horse_last_race.get(horse_name, {})
        last_date = last.get('date')
        days_rest = (race_dt - last_date).days if last_date else 999
        
        # Weight change (scratch_weight - last race draw_weight)
        last_weight = last.get('draw_weight') or 0
        weight_change = int(scratch_weight) - int(last_weight) if scratch_weight and last_weight else 0
        
        # Draw advantage
        draw_advantage = _get_draw_advantage(draw, venue, distance)
        
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
            'jt_place_rate': jt_place_rate,
            'hj_win_rate': hj_win_rate,
            'hj_place_rate': hj_place_rate,
            'draw_dist': draw * distance,
            'hj_races': hj_races.get(hj, 0),
            'days_rest': days_rest,
            'weight_change': weight_change,
            'draw_advantage': draw_advantage,
        })
    
    return results


def predict_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, horse_early_pace, race_date, model, features):
    """Predict race using XGBoost model with pace adjustment"""
    entry_features = build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, race_date, horse_early_pace)
    
    # Add early pace to each feature entry
    for ef in entry_features:
        ef['horse_early_pace'] = horse_early_pace.get(ef['horse_name'], 5.0)
    
    # Build feature matrix (without pace - model doesn't use it yet)
    import numpy as np
    
    X = []
    for ef in entry_features:
        row = []
        for f in features:
            row.append(ef.get(f, 0))
        X.append(row)
    
    X = np.array(X)
    
    # Raw XGBoost predictions (lower score = better predicted rank)
    preds = model.predict(X)
    
    # ---- Pace Analysis Post-Processing ----
    # Race-level pace: average early pace of horses in this race
    paces = [ef['horse_early_pace'] for ef in entry_features]
    race_avg_pace = sum(paces) / len(paces) if paces else 5.0
    
    # Fast pace (low avg) = front-runners dominate → backmarkers disadvantaged
    # Slow pace (high avg) = sit-loom/closers disadvantaged
    # pace_suitability: how well does this horse's style match expected pace?
    #   low horse_early_pace + fast race (low avg) = good match
    #   high horse_early_pace + slow race (high avg) = good match
    PACE_WEIGHT = 0.08  # tuning knob - how much pace adjusts scores
    
    results = []
    for i, ef in enumerate(entry_features):
        horse_pace = ef['horse_early_pace']
        # Positive = horse prefers faster pace than race avg (front-runner in slow race = bad)
        # Negative = horse prefers slower pace than race avg (closer in fast race = bad)
        pace_diff = horse_pace - race_avg_pace  # positive = relatively forward for this race
        
        # Pace bonus: give advantage to horses suited to fast pace when race is slow
        # If horse_pace < race_avg → front-runner → good in fast pace (low race_avg)
        # If pace_diff < 0 and race_avg_pace < 5 (fast race): bonus
        # If pace_diff > 0 and race_avg_pace > 5 (slow race): bonus for closers
        pace_bonus = 0
        if race_avg_pace < 5.0:
            # Fast race: front-runners (low horse_pace) get bonus, closers penalised
            pace_bonus = -pace_diff * PACE_WEIGHT  # negative pace_diff → positive bonus
        elif race_avg_pace > 5.5:
            # Slow race: closers (high horse_pace) get bonus, front-runners penalised
            pace_bonus = pace_diff * PACE_WEIGHT
        # else moderate pace: minimal adjustment
        
        adjusted_score = float(preds[i]) + pace_bonus
        
        results.append({
            'horse_name': ef['horse_name'],
            'jockey': ef['jockey'],
            'trainer': ef['trainer'],
            'draw': ef['draw'],
            'horse_early_pace': round(horse_pace, 1),
            'race_avg_pace': round(race_avg_pace, 1),
            'pace_bonus': round(pace_bonus, 3),
            'raw_score': round(float(preds[i]), 3),
            'score': round(adjusted_score, 3),
        })
    
    # Sort by adjusted score
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
    db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, horse_early_pace = load_data()
    
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
    
    predictions = predict_race(racecard_entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, hj_places, jt_places, horse_last_race, horse_early_pace, race_date, model, features)
    
    print(json.dumps({'predictions': predictions}, ensure_ascii=False))
