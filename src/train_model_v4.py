#!/usr/bin/env python3
"""
HKJC Racing XGBoost Model - Optimized v2
28 Features with finish time
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from src.database.connection import DatabaseConnection
from collections import defaultdict
import xgboost as xgb


def _get_draw_advantage(draw, venue, distance):
    """
    Calculate draw advantage/disadvantage.
    - HV all distances: inner draw (low draw) = advantage
    - ST 1000m: outer draw (high draw) = advantage
    Returns: positive = advantage, negative = disadvantage, 0 = neutral
    """
    if not draw:
        return 0
    if venue == 'HV':
        return 8 - draw   # draw 1 → +7, draw 8 → 0, draw 14 → -6
    if venue == 'ST' and distance == 1000:
        return draw - 8  # draw 14 → +6, draw 8 → 0, draw 1 → -7
    return 0


def _parse_finish_time(ft_str):
    """
    Parse finish_time like '1.10.22' (min.sec.cc) → total seconds as float.
    Returns 0 if unparseable.
    """
    if not ft_str or ft_str == '0':
        return 0
    try:
        parts = ft_str.strip().split('.')
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(ft_str)
    except Exception:
        return 0


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
    
    return db, races, horses, jockeys, trainers, distance_stats


def build_features(races, horses, jockeys, trainers, distance_stats):
    """Build feature matrix"""
    
    # Combo stats
    jt_wins, jt_races, jt_places = defaultdict(int), defaultdict(int), defaultdict(int)
    hj_wins, hj_races, hj_places = defaultdict(int), defaultdict(int), defaultdict(int)
    
    # Horse last race data (for days_rest and weight_change)
    horse_last_race = {}  # horse_name -> {date, weight}
    horse_last_draw = {}  # horse_name -> last race draw_weight
    
    for race in races:
        race_date = race.get('race_date', '')
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
    
    # Track condition wins/runs
    track_cond_wins = defaultdict(int)
    track_cond_runs = defaultdict(int)
    
    # Early pace stats (from running_position)
    early_pace_scores = defaultdict(list)
    
    for race in races:
        track_cond = race.get('track_condition', '好地')
        for r in race.get('results', []):
            horse_name = r.get('horse_name', '')
            running_pos = r.get('running_position', '')
            try: rank = int(r.get('rank', 0)) if r.get('rank') else 0
            except: rank = 0
            
            # Track condition stats
            if horse_name and track_cond:
                track_cond_runs[(horse_name, track_cond)] += 1
                if rank == 1: track_cond_wins[(horse_name, track_cond)] += 1
            
            # Early pace (parse first position from "1 2 3" pattern)
            if running_pos and horse_name:
                parts = running_pos.split()
                if parts:
                    try:
                        first_pos = int(parts[0])
                        # Lower first position = front-runner = higher pace score
                        # Invert so high score = front-runner
                        early_pace_scores[horse_name].append(first_pos)
                    except: pass
    
    # Calculate avg early pace (lower = front-runner)
    avg_early_pace = {h: sum(scores)/len(scores) for h, scores in early_pace_scores.items() if scores}
    
    # Calculate track condition win rates
    track_cond_winrate = {}
    for (horse, cond), wins in track_cond_wins.items():
        runs = track_cond_runs.get((horse, cond), 0)
        if runs > 0:
            track_cond_winrate[(horse, cond)] = wins / runs
    
    # Build distance + venue stats from race history
    dist_time_stats = defaultdict(list)
    venue_dist_time_stats = defaultdict(list)
    
    for rh in db.db['horse_race_history'].find({}):
        try:
            ft = _parse_finish_time(rh.get('finish_time', ''))
            dist = int(rh.get('distance', 0))
            venue = rh.get('venue', '')
            if ft > 0 and dist > 0:
                dist_time_stats[dist].append(ft)
                # Extract venue from venue string (e.g., "沙田草地\"C\"" -> "ST")
                v_key = 'HV' if '跑馬地' in venue or 'HV' in venue else 'ST'
                venue_dist_time_stats[(v_key, dist)].append(ft)
        except: pass
    
    # Calculate best times for each distance and venue+distance
    dist_best_time = {d: min(times) for d, times in dist_time_stats.items() if times}
    venue_dist_best = {}
    for (v, d), times in venue_dist_time_stats.items():
        venue_dist_best[(v, d)] = min(times)
    
    # Race history with finish times
    race_history = {}
    for rh in db.db['horse_race_history'].find({}):
        hid = rh.get('hkjc_horse_id')
        if hid:
            if hid not in race_history: race_history[hid] = []
            try: rank = int(rh.get('position', 0)) if rh.get('position') else 0
            except: rank = 0
            finish_time = rh.get('finish_time', '')
            ft = _parse_finish_time(finish_time)
            race_history[hid].append({'date': rh.get('date', ''), 'rank': rank, 'distance': rh.get('distance', 0), 'venue': rh.get('venue', ''), 'finish_time': ft})
    
    for hid in race_history: race_history[hid].sort(key=lambda x: x.get('date', ''), reverse=True)
    
    # Average best time per distance
    dist_best_time = {}
    for hid, hist in race_history.items():
        for h in hist:
            d = h.get('distance', 0)
            ft = h.get('finish_time', 0)
            if d and ft > 0:
                if d not in dist_best_time: dist_best_time[d] = []
                dist_best_time[d].append(ft)
    avg_best_time = {d: sum(t)/len(t) for d, t in dist_best_time.items() if t}
    
    samples = []
    for race in races:
        race_id = race.get('race_id', '') or race.get('hkjc_race_id', '')
        race_dist, race_venue = race.get('distance', 0) or 0, race.get('venue', '')
        
        race_ratings = [horses.get(r.get('horse_name', '')).get('current_rating', 0) for r in race.get('results', []) if horses.get(r.get('horse_name', ''))]
        race_avg = sum(race_ratings)/len(race_ratings) if race_ratings else 0
        
        for r in race.get('results', []):
            try: rank = int(r.get('rank', 0)) if r.get('rank') else 0
            except: rank = 0
            if rank == 0: continue
            
            horse_name, jockey_name, trainer_name = r.get('horse_name', ''), r.get('jockey', ''), r.get('trainer', '')
            draw = int(r.get('draw', 0) or 0)
            horse = horses.get(horse_name)
            hid = horse.get('hkjc_horse_id', '') if horse else ''
            
            current_rating = int(horse.get('current_rating', 0) or 0) if horse else 0
            career_starts = int(horse.get('career_starts', 0) or 0) if horse else 0
            career_wins = int(horse.get('career_wins', 0) or 0) if horse else 0
            career_seconds = int(horse.get('career_seconds', 0) or 0) if horse else 0
            career_thirds = int(horse.get('career_thirds', 0) or 0) if horse else 0
            season_prize = int(horse.get('season_prize', 0) or 0) if horse else 0
            
            ds = distance_stats.get(hid, {})
            dp, tp = ds.get('distance_performance', []), ds.get('track_performance', [])
            
            dist_wins = dist_runs = dist_win_rate = 0
            for d in dp:
                if f'{race_dist}米' in d.get('distance', ''):
                    dist_runs = int(d.get('total_runs', 0) or 0)
                    dist_wins = int(d.get('first', 0) or 0)
                    dist_win_rate = dist_wins / dist_runs if dist_runs > 0 else 0
                    break
            
            track_wins = track_runs = track_win_rate = 0
            for t in tp:
                if '草地' in t.get('surface', ''):
                    track_runs = int(t.get('starts', 0) or 0)
                    track_wins = int(t.get('win', 0) or 0)
                    track_win_rate = track_wins / track_runs if track_runs > 0 else 0
                    break
            
            # Recent 3
            recent_3_ranks = []
            recent_venue_ranks = []
            best_finish = None
            if hid in race_history:
                for rh in race_history[hid][:3]:
                    if rh.get('rank'): recent_3_ranks.append(rh.get('rank'))
                    if rh.get('venue') == race_venue and rh.get('rank'): recent_venue_ranks.append(rh.get('rank'))
                for rh in race_history[hid][:20]:
                    if rh.get('distance') == race_dist and rh.get('finish_time', 0) > 0:
                        if best_finish is None or rh.get('finish_time', 0) < best_finish:
                            best_finish = rh.get('finish_time', 0)
            
            recent3_avg = sum(recent_3_ranks)/len(recent_3_ranks) if recent_3_ranks else 0
            recent3_wins = sum(1 for r in recent_3_ranks if r == 1)
            venue_avg = sum(recent_venue_ranks)/len(recent_venue_ranks) if recent_venue_ranks else 0
            
            dist_avg = avg_best_time.get(race_dist, 0)
            finish_diff = dist_avg - best_finish if best_finish and dist_avg else 0
            
            # Combos
            jt_wr = jt_wins.get((jockey_name, trainer_name), 0) / jt_races.get((jockey_name, trainer_name), 1) if jt_races.get((jockey_name, trainer_name), 0) > 0 else 0
            
            # Best time for this distance and venue+distance
            best_dist_time = dist_best_time.get(race_dist, 0)
            best_venue_dist_time = venue_dist_best.get((race_venue, race_dist), 0)
            
            # New: Track condition adaptation
            tc_wr = track_cond_winrate.get((horse_name, track_cond), 0)
            tc_runs = track_cond_runs.get((horse_name, track_cond), 0)
            
            # New: Early pace score (lower = front-runner, higher = closer)
            avg_ep = avg_early_pace.get(horse_name, 10)  # default 10 = unknown/very slow early
            
            # New: Weight advantage (lighter = better, typical min ~113)
            # actual_weight from race result if available, else 0
            actual_wt = r.get('actual_weight', 0) if 'r' in dir() else 0
            weight_advantage = max(0, 120 - actual_wt) if actual_wt > 0 else 0
            
            j = jockeys.get(jockey_name) or {}
            j_wr = (j.get('wins') or 0) / max(1, j.get('total_rides') or 0) if j else 0
            j_places = (j.get('seconds') or 0) + (j.get('thirds') or 0) + (j.get('wins') or 0)
            j_place_rate = j_places / max(1, j.get('total_rides') or 0) if j else 0
            
            t = trainers.get(trainer_name)
            t_wr = (t.get('wins', 0) or 0) / max(1, t.get('total_horses', 0) or 0) if t else 0
            
            career_place = career_wins + career_seconds + career_thirds
            cpr = career_place / career_starts if career_starts > 0 else 0
            
            # HJ / JT place rates (replacing win rates as more stable signal)
            hj_key = (horse_name, jockey_name)
            hj_place_rate = hj_places.get(hj_key, 0) / hj_races.get(hj_key, 1) if hj_races.get(hj_key, 0) > 0 else 0
            jt_key = (jockey_name, trainer_name)
            jt_place_rate = jt_places.get(jt_key, 0) / jt_races.get(jt_key, 1) if jt_races.get(jt_key, 0) > 0 else 0
            
            # Draw advantage
            draw_adv = _get_draw_advantage(draw, race_venue, race_dist)
            
            samples.append({
                'race_id': race_id, 'horse_name': horse_name, 'draw': draw, 'distance': race_dist,
                'venue': 1 if race_venue == 'HV' else 0, 'current_rating': current_rating,
                'career_starts': career_starts, 'career_wins': career_wins, 'career_place_rate': cpr,
                'season_prize': season_prize, 'dist_wins': dist_wins, 'dist_runs': dist_runs, 'dist_win_rate': dist_win_rate,
                'track_wins': track_wins, 'track_runs': track_runs, 'track_win_rate': track_win_rate,
                'recent3_avg_rank': recent3_avg, 'recent3_wins': recent3_wins, 'venue_avg_rank': venue_avg,
                'jockey_win_rate': j_wr, 'jockey_place_rate': j_place_rate,
                'trainer_win_rate': t_wr,
                'jt_place_rate': jt_place_rate,
                'jt_races': jt_races.get((jockey_name, trainer_name), 0),
                'best_dist_time': best_dist_time,
                'best_venue_dist_time': best_venue_dist_time,
                'best_finish_time': best_finish if best_finish else 0,
                'finish_time_diff': finish_diff,
                'draw_dist': draw * race_dist, 'draw_rating': draw * current_rating,
                'track_cond_winrate': tc_wr,
                'track_cond_runs': tc_runs,
                'early_pace_score': avg_ep,
                'weight_advantage': weight_advantage,
                'draw_advantage': draw_adv,
                # Target variable (not a feature)
                'actual_rank': rank,
            })
    
    return pd.DataFrame(samples)


def train_and_evaluate(df):
    """Train model and evaluate"""
    features = [
        'career_starts', 'career_wins', 'career_place_rate', 'season_prize',
        'dist_wins', 'dist_runs', 'dist_win_rate',
        'track_wins', 'track_runs', 'track_win_rate',
        'recent3_avg_rank', 'recent3_wins', 'venue_avg_rank',
        'jockey_win_rate', 'jockey_place_rate',
        'trainer_win_rate',
        'jt_place_rate', 'jt_races',
        'best_dist_time', 'best_venue_dist_time',
        'best_finish_time', 'finish_time_diff',
        'draw_dist', 'draw_rating',
        'track_cond_winrate', 'track_cond_runs',
        'early_pace_score', 'weight_advantage',
        'draw_advantage',
    ]
    
    X = df[features].fillna(0).replace([float('inf'), float('-inf')], 0)
    X_scaled = StandardScaler().fit_transform(X)
    
    # Split by race
    unique_race_ids = df['race_id'].unique()
    np.random.seed(42)
    np.random.shuffle(unique_race_ids)
    split_idx = int(len(unique_race_ids) * 0.8)
    train_mask = df['race_id'].isin(set(unique_race_ids[:split_idx]))
    test_mask = df['race_id'].isin(set(unique_race_ids[split_idx:]))
    
    X_train, y_train = X_scaled[train_mask], df.loc[train_mask, 'actual_rank']
    X_test = X_scaled[test_mask]
    
    # Train XGBoost with regularization
    model = xgb.XGBRegressor(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        reg_alpha=0.5,   # L1 — penalize large weights, spread importance
        reg_lambda=1.0,  # L2 — smooth out dominant features
        random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)
    
    # Evaluate
    test_df = df[test_mask].copy()
    test_df['pred'] = model.predict(X_test)
    
    c1, t3, n = 0, 0, 0
    for rid in test_df['race_id'].unique():
        rh = test_df[test_df['race_id']==rid].sort_values('pred')
        if len(rh) < 3: continue
        n += 1
        c1 += 1 if rh.iloc[0]['horse_name'] == rh[rh['actual_rank']==1]['horse_name'].values[0] else 0
        t3 += len(set(rh.head(3)['horse_name']) & set(rh[rh['actual_rank']<=3]['horse_name']))
    
    print(f'Results: 1st={c1/n*100:.1f}%, Top3={t3/n:.2f}')
    print(f'Features: {len(features)}')
    
    print('\nTop Features:')
    for f, i in sorted(zip(features, model.feature_importances_), key=lambda x: -x[1])[:20]:
        print(f'  {i:.4f}  {f}')
    
    return model, features


if __name__ == '__main__':
    import pickle
    
    print('Loading data...')
    db, races, horses, jockeys, trainers, distance_stats = load_data()
    
    print('Building features...')
    df = build_features(races, horses, jockeys, trainers, distance_stats)
    print(f'Samples: {len(df)}')
    
    print('Training model...')
    model, features = train_and_evaluate(df)
    
    # Save model
    with open('xgb_model.pkl', 'wb') as f:
        pickle.dump({'model': model, 'features': features}, f)
    print('\nModel saved to xgb_model.pkl')
