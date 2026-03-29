#!/usr/bin/env python3
"""
XGBoost Model Prediction Script
"""
import sys
import os
import json
import pickle

sys.path.insert(0, '/app')
os.environ['PYTHONUNBUFFERED'] = '1'

from src.database.connection import DatabaseConnection
from collections import defaultdict


def load_model():
    """Load XGBoost model"""
    with open('/app/xgb_model.pkl', 'rb') as f:
        data = pickle.load(f)
    return data['model'], data['features']


def _parse_finish_time(ft_str):
    """Parse finish time string like '1.10.22' to seconds."""
    if not ft_str:
        return None
    try:
        parts = str(ft_str).strip().split('.')
        if len(parts) >= 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100
        return None
    except (ValueError, TypeError):
        return None


def _normalize_venue(venue_str):
    """Normalize venue string to HV/ST."""
    v = str(venue_str).upper()
    if 'HV' in v or '快活谷' in v:
        return 'HV'
    return 'ST'


def _normalize_track_condition(tc_str):
    """Normalize track condition string."""
    tc = str(tc_str).strip()
    if tc in ('好', 'GOOD', 'G', 'A', 'A+'):
        return 'GOOD'
    if tc in ('好至正常', '好至頗慢'):
        return 'GOOD_TO_FAVORABLE'
    if tc in ('正常', 'NORMAL', 'N', 'B'):
        return 'NORMAL'
    if tc in ('濕', 'WET', 'W', 'C'):
        return 'WET'
    return 'NORMAL'


def _compute_horse_history_stats(db):
    """Pre-compute aggregated stats per horse from horse_race_history collection.
    
    Returns dict: { hkjc_horse_id: { feature_name: value, ... } }
    """
    from collections import defaultdict
    
    # Aggregate all history records per horse
    history_records = defaultdict(list)
    for rec in db.db['horse_race_history'].find({}):
        hid = rec.get('hkjc_horse_id')
        if not hid:
            continue
        history_records[hid].append(rec)
    
    stats = {}
    for hid, recs in history_records.items():
        s = {}
        
        # ---- track_wins, track_runs, track_win_rate ----
        track_wins = track_runs = 0
        for r in recs:
            pos = r.get('position', '')
            try:
                rank = int(pos) if pos else 0
            except (ValueError, TypeError):
                rank = 0
            if rank > 0:
                track_runs += 1
                if rank == 1:
                    track_wins += 1
        s['track_wins'] = track_wins
        s['track_runs'] = track_runs
        s['track_win_rate'] = track_wins / track_runs if track_runs > 0 else 0
        
        # ---- recent3_avg_rank, recent3_wins ----
        # Sort by date descending
        sorted_recs = sorted(recs, key=lambda r: r.get('date', ''), reverse=True)
        recent3 = sorted_recs[:3]
        ranks = []
        recent3_wins = 0
        for r in recent3:
            pos = r.get('position', '')
            try:
                rank = int(pos) if pos else 0
            except (ValueError, TypeError):
                rank = 0
            if rank > 0:
                ranks.append(rank)
                if rank == 1:
                    recent3_wins += 1
        s['recent3_avg_rank'] = sum(ranks) / len(ranks) if ranks else 5
        s['recent3_wins'] = recent3_wins
        
        # ---- venue_avg_rank ----
        venue_ranks = []
        for r in recs:
            pos = r.get('position', '')
            try:
                rank = int(pos) if pos else 0
            except (ValueError, TypeError):
                rank = 0
            if rank > 0:
                venue_ranks.append(rank)
        s['venue_avg_rank'] = sum(venue_ranks) / len(venue_ranks) if venue_ranks else 5
        
        # ---- best_dist_time, best_venue_dist_time ----
        dist_times = {}
        venue_dist_times = {}
        for r in recs:
            ft = _parse_finish_time(r.get('finish_time'))
            if ft is None:
                continue
            dist = str(r.get('distance', '')).replace('米', '').strip()
            venue = _normalize_venue(r.get('venue', ''))
            dist_key = int(dist) if dist.isdigit() else None
            venue_dist_key = f"{venue}_{dist_key}"
            
            if dist_key:
                if dist_key not in dist_times or ft < dist_times[dist_key]:
                    dist_times[dist_key] = ft
                vd_key = f"{venue}_{dist_key}"
                if vd_key not in venue_dist_times or ft < venue_dist_times[vd_key]:
                    venue_dist_times[vd_key] = ft
        
        # Get best for a given distance placeholder (filled by build_features_for_race)
        s['_best_dist_times'] = dist_times
        s['_best_venue_dist_times'] = venue_dist_times
        
        # ---- best_finish_time (overall best) ----
        all_times = [_parse_finish_time(r.get('finish_time')) for r in recs]
        all_times = [t for t in all_times if t is not None]
        s['best_finish_time'] = min(all_times) if all_times else 0
        
        # ---- track_cond_winrate, track_cond_runs ----
        tc_wins = defaultdict(int)
        tc_runs = defaultdict(int)
        for r in recs:
            tc = _normalize_track_condition(r.get('track_condition', ''))
            pos = r.get('position', '')
            try:
                rank = int(pos) if pos else 0
            except (ValueError, TypeError):
                rank = 0
            tc_runs[tc] += 1
            if rank == 1:
                tc_wins[tc] += 1
        # Store all for lookup by race condition (default to GOOD)
        s['_tc_wins'] = dict(tc_wins)
        s['_tc_runs'] = dict(tc_runs)
        s['track_cond_winrate'] = 0  # default
        s['track_cond_runs'] = 0      # default
        
        stats[hid] = s
    
    return stats


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
    
    # Pre-compute horse history stats from horse_race_history
    horse_history_stats = _compute_horse_history_stats(db)
    
    # Imports must be at function top (Python treats 'from X import Y' as local for entire function)
    from collections import defaultdict
    from datetime import datetime
    
    # Build combo stats
    jt_wins, jt_races = defaultdict(int), defaultdict(int)
    hj_wins, hj_races = defaultdict(int), defaultdict(int)
    jt_places = defaultdict(int)
    
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
    
    return db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, horse_early_pace, horse_history_stats


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


def build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, race_date, horse_early_pace, horse_history_stats):
    """Build features for race entries — produces all 29 model features."""
    results = []
    
    # Pre-calculate race-average weight for weight_advantage
    scratch_weights = []
    for e in entries:
        sw = e.get('scratch_weight', 0) or 0
        if sw:
            scratch_weights.append(int(sw))
    race_avg_weight = sum(scratch_weights) / len(scratch_weights) if scratch_weights else 1200
    
    for entry in entries:
        horse_name = entry.get('horse_name', '')
        jockey = entry.get('jockey_name', '')
        trainer = entry.get('trainer_name', '')
        draw_raw = entry.get('draw', 0)
        if isinstance(draw_raw, str):
            try:
                draw = int(float(draw_raw))
            except (ValueError, TypeError):
                draw = 0
        else:
            draw = int(draw_raw) if draw_raw else 0
        
        scratch_weight_raw = entry.get('scratch_weight', 0)
        if isinstance(scratch_weight_raw, str):
            try:
                scratch_weight = int(float(scratch_weight_raw))
            except (ValueError, TypeError):
                scratch_weight = 0
        else:
            scratch_weight = int(scratch_weight_raw) if scratch_weight_raw else 0
        
        horse = horses.get(horse_name, {})
        hid = horse.get('hkjc_horse_id', '') if horse else ''
        
        current_rating = int(horse.get('current_rating', 0) or 0) if horse else 0
        career_starts = int(horse.get('career_starts', 0) or 0) if horse else 0
        career_wins = int(horse.get('career_wins', 0) or 0) if horse else 0
        career_seconds = int(horse.get('career_seconds', 0) or 0) if horse else 0
        career_thirds = int(horse.get('career_thirds', 0) or 0) if horse else 0
        season_prize = float(horse.get('season_prize', 0) or 0) if horse else 0
        
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
        
        # Pre-computed horse history stats
        hhs = horse_history_stats.get(hid, {})
        
        # track_wins, track_runs, track_win_rate
        track_wins = hhs.get('track_wins', 0)
        track_runs = hhs.get('track_runs', 0)
        track_win_rate = hhs.get('track_win_rate', 0)
        
        # recent3_avg_rank, recent3_wins
        recent3_avg_rank = hhs.get('recent3_avg_rank', 5.0)
        recent3_wins = hhs.get('recent3_wins', 0)
        
        # venue_avg_rank
        venue_avg_rank = hhs.get('venue_avg_rank', 5.0)
        
        # Jockey-trainer combo
        jt = (jockey, trainer)
        jt_win_rate = jt_wins.get(jt, 0) / jt_races.get(jt, 1) if jt_races.get(jt, 0) > 0 else 0
        jt_place_rate = jt_places.get(jt, 0) / jt_races.get(jt, 1) if jt_races.get(jt, 0) > 0 else 0
        
        # Horse-jockey combo
        hj = (horse_name, jockey)
        hj_win_rate = hj_wins.get(hj, 0) / hj_races.get(hj, 1) if hj_races.get(hj, 0) > 0 else 0
        
        # Jockey
        j = jockeys.get(jockey, {})
        jockey_win_rate = (j.get('wins', 0) or 0) / max(1, (j.get('total_rides', 0) or 0)) if j else 0
        jockey_place_rate = 0  # jockeys collection may not have this
        
        # Trainer
        t = trainers.get(trainer, {})
        trainer_win_rate = (t.get('wins', 0) or 0) / max(1, (t.get('total_horses', 0) or 0)) if t else 0
        trainer_place_rate = 0  # trainers collection may not have this
        
        # Best times from pre-computed history
        dist_times_map = hhs.get('_best_dist_times', {})
        venue_dist_map = hhs.get('_best_venue_dist_times', {})
        best_dist_time = dist_times_map.get(distance, 0)
        best_venue_dist_time = venue_dist_map.get(f'{venue}_{distance}', 0)
        best_finish_time = hhs.get('best_finish_time', 0)
        
        # finish_time_diff: diff from race average finish time (approximate with best_dist_time)
        # We compute as: if best_dist_time exists, diff from expected avg
        # For now, set to 0 since we don't have race avg easily
        finish_time_diff = 0
        
        # Track condition stats — default to horse's overall performance
        tc_wins = hhs.get('_tc_wins', {})
        tc_runs = hhs.get('_tc_runs', {})
        track_cond_winrate = tc_wins.get('GOOD', 0) / max(1, tc_runs.get('GOOD', 0))
        track_cond_runs = tc_runs.get('GOOD', 0)
        
        # Draw advantage
        draw_advantage = _get_draw_advantage(draw, venue, distance)
        
        # draw_rating: simplified from draw_advantage (no separate historical draw rating available)
        draw_rating = draw_advantage
        
        # Early pace score (pre-computed from races results)
        early_pace_score = horse_early_pace.get(horse_name, 5.0)
        
        # Weight advantage vs race average
        sw_int = int(scratch_weight) if scratch_weight else 0
        weight_advantage = race_avg_weight - sw_int  # lower weight = higher advantage
        
        results.append({
            'horse_name': horse_name,
            'horse_no': entry.get('horse_no', 0),
            'jockey': jockey,
            'trainer': trainer,
            'draw': draw,
            # Model features (29 in order from xgb_model.pkl):
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
            'recent3_avg_rank': recent3_avg_rank,
            'recent3_wins': recent3_wins,
            'venue_avg_rank': venue_avg_rank,
            'jockey_win_rate': jockey_win_rate,
            'jockey_place_rate': jockey_place_rate,
            'trainer_win_rate': trainer_win_rate,
            'jt_place_rate': jt_place_rate,
            'jt_races': jt_races.get(jt, 0),
            'best_dist_time': best_dist_time,
            'best_venue_dist_time': best_venue_dist_time,
            'best_finish_time': best_finish_time,
            'finish_time_diff': finish_time_diff,
            'draw_dist': draw * distance,
            'draw_rating': draw_rating,
            'track_cond_winrate': track_cond_winrate,
            'track_cond_runs': track_cond_runs,
            'early_pace_score': early_pace_score,
            'weight_advantage': weight_advantage,
            'draw_advantage': draw_advantage,
        })
    
    return results


def predict_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, horse_early_pace, race_date, model, features, boosting=None, horse_history_stats=None):
    """Predict race with optional feature boosting.
    
    boosting: dict of group_name or feature_name -> multiplier (default 1.0)
    Groups: distance, jockey, recent, track, draw, career, trainer, best_time, pace
    """
    # Map frontend group names to actual feature names
    GROUP_FEATURES = {
        'distance': ['dist_wins', 'dist_win_rate', 'dist_runs', 'best_dist_time', 'best_venue_dist_time'],
        'jockey': ['jockey_win_rate', 'jockey_place_rate', 'jt_place_rate', 'jt_races'],
        'recent': ['recent3_avg_rank', 'recent3_wins'],
        'track': ['track_cond_winrate', 'track_cond_runs', 'track_wins', 'track_runs', 'track_win_rate'],
        'draw': ['draw_dist', 'draw_rating', 'draw_advantage'],
        'career': ['career_starts', 'career_wins', 'career_place_rate', 'season_prize'],
        'trainer': ['trainer_win_rate', 'trainer_place_rate'],
        'best_time': ['best_finish_time', 'best_dist_time', 'best_venue_dist_time', 'finish_time_diff'],
        'pace': ['early_pace_score'],
    }
    
    # Expand group-level boosting to feature-level
    expanded_boost = {}
    if boosting:
        for group, mult in boosting.items():
            if group in GROUP_FEATURES:
                for feat in GROUP_FEATURES[group]:
                    expanded_boost[feat] = mult
            else:
                expanded_boost[group] = mult
    
    entry_features = build_features_for_race(entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, race_date, horse_early_pace, horse_history_stats or {})
    
    # Add early pace to each feature entry
    for ef in entry_features:
        ef['horse_early_pace'] = horse_early_pace.get(ef['horse_name'], 5.0)
    
    # Build feature matrix (with optional boosting)
    import numpy as np
    
    X = []
    for ef in entry_features:
        row = []
        for f in features:
            val = ef.get(f, 0) or 0
            # Convert to numeric: strings like '7' for draw → int 7
            if isinstance(val, str):
                try:
                    val = int(float(val))
                except (ValueError, TypeError):
                    val = 0
            elif not isinstance(val, (int, float)):
                val = 0
            boost = expanded_boost.get(f, 1.0)
            row.append(val * boost)
        X.append(row)
    
    X = np.array(X)
    
    # Guard: if no entries, return empty predictions
    if len(entry_features) == 0:
        return [], 0.0
    
    # Ensure X is 2D with correct number of features
    if X.ndim == 1:
        # Malformed - reshape or bail
        if X.size == len(features):
            X = X.reshape(1, len(features))
        else:
            X = np.zeros((len(entry_features), len(features)))
    elif X.shape[1] != len(features):
        # Feature count mismatch - rebuild X row by row with safe defaults
        X = np.zeros((len(entry_features), len(features)))
        for i, ef in enumerate(entry_features):
            for j, f in enumerate(features):
                X[i, j] = ef.get(f, 0) or 0
    
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
            'horse_no': ef.get('horse_no', 0),
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
    
    # Confidence score: sum of raw scores for top 4 (lower raw = better predicted)
    # This reflects how "clear" the model's verdict is for this race
    top4_raw_sum = sum(results[i]['raw_score'] for i in range(min(4, len(results))))
    # Invert: raw_score low = confident prediction, so invert to get confidence where HIGHER = more confident
    race_confidence = round(100 - top4_raw_sum, 2)
    
    return results, race_confidence


if __name__ == '__main__':
    import sys
    
    race_date = sys.argv[1] if len(sys.argv) > 1 else '2026-03-18'
    race_no = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    venue = sys.argv[3] if len(sys.argv) > 3 else 'HV'
    boosting = None
    if len(sys.argv) > 4 and sys.argv[4] != 'null':
        try:
            import json
            boosting = json.loads(sys.argv[4])
        except Exception:
            pass
    
    import sys
    sys.stderr.write(f'Loading model and data for {race_date} R{race_no} {venue}...' + (f' boosting={boosting}' if boosting else '') + '\n')
    sys.stderr.flush()
    
    model, features = load_model()
    db, races, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, horse_early_pace, horse_history_stats = load_data()
    
    # Get racecard entries (exclude scratched horses)
    racecard_entries = list(db.db['racecard_entries'].find({
        'race_date': race_date,
        'venue': venue,
        'race_no': race_no,
        'status': {'$ne': 'Scratched'}
    }))
    
    # Fallback: if racecard_entries is empty, extract from racecards' embedded horses
    if not racecard_entries:
        racecard = db.db['racecards'].find_one({
            'race_date': race_date,
            'venue': venue,
            'race_no': race_no
        })
        if racecard and racecard.get('horses'):
            racecard_entries = []
            for h in racecard['horses']:
                # Skip standby/non-declared horses
                hn = h.get('horse_no', 0)
                if isinstance(hn, str):
                    try:
                        hn = int(float(hn))
                    except:
                        hn = 0
                if h.get('status') in ('Standby', 'Scratched') or hn == 0:
                    continue
                # Normalize draw to int
                draw_raw = h.get('draw', 0)
                if isinstance(draw_raw, str):
                    try:
                        h['draw'] = int(float(draw_raw))
                    except:
                        h['draw'] = 0
                racecard_entries.append(h)
    
    racecard = db.db['racecards'].find_one({
        'race_date': race_date,
        'venue': venue,
        'race_no': race_no
    })
    
    distance = racecard.get('distance', 1200) if racecard else 1200
    
    predictions, race_confidence = predict_race(racecard_entries, distance, venue, horses, jockeys, trainers, distance_stats, jt_wins, jt_races, hj_wins, hj_races, jt_places, horse_last_race, horse_early_pace, race_date, model, features, boosting, horse_history_stats)
    
    print(json.dumps({'predictions': predictions, 'race_confidence': race_confidence}, ensure_ascii=False))
