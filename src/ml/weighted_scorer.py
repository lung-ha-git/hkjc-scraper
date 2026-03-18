#!/usr/bin/env python3
"""
Weighted Scoring System for HKJC Racing Predictions
Allows manual adjustment of factor weights to find optimal combinations
"""

import pandas as pd
import numpy as np
from src.database.connection import DatabaseConnection
from collections import defaultdict


class WeightedScorer:
    """
    Weighted scoring system for horse racing predictions
    
    Usage:
        scorer = WeightedScorer()
        scorer.load_data()
        
        # Set custom weights
        weights = {
            'hj_win_rate': 10,
            'career_place_rate': 5,
            'jockey_win_rate': 3,
            ...
        }
        
        # Get predictions for a race
        predictions = scorer.predict_race(race_id, weights)
    """
    
    def __init__(self):
        self.db = None
        self.races = []
        self.horses = {}
        self.jockeys = {}
        self.trainers = {}
        self.distance_stats = {}
        self.jt_combo = {}
        self.hj_combo = {}
        self.race_history = {}
        
    def load_data(self):
        """Load all necessary data from MongoDB"""
        # print("Loading data...")
        self.db = DatabaseConnection()
        self.db.connect()
        
        self.races = list(self.db.db['races'].find({}).sort('race_date', 1))
        
        self.horses = {h.get('name', ''): h for h in self.db.db['horses'].find({})}
        self.horses.update({h.get('hkjc_horse_id'): h for h in self.db.db['horses'].find({})})
        
        self.jockeys = {j.get('name', ''): j for j in self.db.db['jockeys'].find({})}
        self.trainers = {t.get('name', ''): t for t in self.db.db['trainers'].find({})}
        self.distance_stats = {ds.get('hkjc_horse_id'): ds for ds in self.db.db['horse_distance_stats'].find({})}
        
        # Build combo stats
        for race in self.races:
            for r in race.get('results', []):
                jockey = r.get('jockey', '')
                trainer = r.get('trainer', '')
                horse_name = r.get('horse_name', '')
                try:
                    rank = int(r.get('rank', 0)) if r.get('rank') else 0
                except Exception:
                    rank = 0
                
                if jockey and trainer:
                    key = (jockey, trainer)
                    if key not in self.jt_combo:
                        self.jt_combo[key] = {'wins': 0, 'races': 0}
                    self.jt_combo[key]['races'] += 1
                    if rank == 1:
                        self.jt_combo[key]['wins'] += 1
                
                if horse_name and jockey:
                    key = (horse_name, jockey)
                    if key not in self.hj_combo:
                        self.hj_combo[key] = {'wins': 0, 'races': 0}
                    self.hj_combo[key]['races'] += 1
                    if rank == 1:
                        self.hj_combo[key]['wins'] += 1
        
        # Race history
        for rh in self.db.db['horse_race_history'].find({}):
            hid = rh.get('hkjc_horse_id')
            if hid:
                if hid not in self.race_history:
                    self.race_history[hid] = []
                try:
                    rank = int(rh.get('position', 0)) if rh.get('position') else 0
                except Exception:
                    rank = 0
                self.race_history[hid].append({
                    'date': rh.get('date', ''),
                    'rank': rank,
                    'distance': rh.get('distance', 0),
                    'venue': rh.get('venue', '')
                })
        
        for hid in self.race_history:
            self.race_history[hid].sort(key=lambda x: x.get('date', ''), reverse=True)
        
        # print(f"Loaded {len(self.races)} races")
    
    def get_horse_features(self, horse_name, jockey_name, trainer_name, race_distance, race_venue):
        """Get features for a horse in a specific race context"""
        
        horse = self.horses.get(horse_name)
        hid = horse.get('hkjc_horse_id', '') if horse else ''
        
        # Basic info
        current_rating = int(horse.get('current_rating', 0) or 0) if horse else 0
        career_starts = int(horse.get('career_starts', 0) or 0) if horse else 0
        career_wins = int(horse.get('career_wins', 0) or 0) if horse else 0
        career_seconds = int(horse.get('career_seconds', 0) or 0) if horse else 0
        career_thirds = int(horse.get('career_thirds', 0) or 0) if horse else 0
        
        # Career place rate
        career_place = career_wins + career_seconds + career_thirds
        career_place_rate = career_place / career_starts if career_starts > 0 else 0
        
        # Distance performance
        ds = self.distance_stats.get(hid, {})
        dp = ds.get('distance_performance', [])
        
        dist_wins = dist_runs = dist_win_rate = 0
        dist_str = f'{race_distance}米'
        for d in dp:
            if dist_str in d.get('distance', ''):
                dist_runs = int(d.get('total_runs', 0) or 0)
                dist_wins = int(d.get('first', 0) or 0)
                dist_win_rate = dist_wins / dist_runs if dist_runs > 0 else 0
                break
        
        # Recent 3 races
        recent_3_ranks = []
        if hid in self.race_history:
            for rh in self.race_history[hid][:3]:
                if rh.get('rank'):
                    recent_3_ranks.append(rh.get('rank'))
        
        recent3_avg_rank = sum(recent_3_ranks) / len(recent_3_ranks) if recent_3_ranks else 0
        recent3_wins = sum(1 for r in recent_3_ranks if r == 1)
        
        # Jockey-trainer combo
        jt = self.jt_combo.get((jockey_name, trainer_name), {'wins': 0, 'races': 0})
        jt_win_rate = jt['wins'] / jt['races'] if jt['races'] > 0 else 0
        
        # Horse-jockey combo
        hj = self.hj_combo.get((horse_name, jockey_name), {'wins': 0, 'races': 0})
        hj_win_rate = hj['wins'] / hj['races'] if hj['races'] > 0 else 0
        
        # Jockey
        j = self.jockeys.get(jockey_name)
        jockey_win_rate = (j.get('wins', 0) or 0) / max(1, (j.get('total_rides', 0) or 0)) if j else 0
        
        # Trainer
        t = self.trainers.get(trainer_name)
        trainer_win_rate = (t.get('wins', 0) or 0) / max(1, (t.get('total_horses', 0) or 0)) if t else 0
        
        return {
            'horse_name': horse_name,
            'draw': 0,  # Will be set per race
            'distance': race_distance,
            'venue': 1 if race_venue == 'HV' else 0,
            'current_rating': current_rating,
            'relative_rating': 0,  # Need race context
            'career_starts': career_starts,
            'career_wins': career_wins,
            'career_place_rate': career_place_rate,
            'dist_wins': dist_wins,
            'dist_runs': dist_runs,
            'dist_win_rate': dist_win_rate,
            'recent3_avg_rank': recent3_avg_rank,
            'recent3_wins': recent3_wins,
            'jockey_win_rate': jockey_win_rate,
            'trainer_win_rate': trainer_win_rate,
            'jt_win_rate': jt_win_rate,
            'hj_win_rate': hj_win_rate,
            'draw_dist': 0,
        }
    
    def predict_race(self, race_id, weights):
        """
        Predict race results using weighted scoring
        
        Args:
            race_id: Race ID
            weights: Dict of feature weights
            
        Returns:
            List of horses ranked by score
        """
        race = None
        for r in self.races:
            if r.get('race_id') == race_id or r.get('hkjc_race_id') == race_id:
                race = r
                break
        
        if not race:
            return {"error": "Race not found"}
        
        race_distance = race.get('distance', 0) or 0
        race_venue = race.get('venue', '')
        
        # Get race average rating for relative rating
        race_ratings = []
        for r in race.get('results', []):
            horse = self.horses.get(r.get('horse_name', ''))
            if horse:
                rating = horse.get('current_rating', 0) or 0
                if rating:
                    race_ratings.append(rating)
        race_avg_rating = sum(race_ratings) / len(race_ratings) if race_ratings else 0
        
        results = []
        for r in race.get('results', []):
            horse_name = r.get('horse_name', '')
            jockey_name = r.get('jockey', '')
            trainer_name = r.get('trainer', '')
            draw = int(r.get('draw', 0) or 0)
            
            features = self.get_horse_features(horse_name, jockey_name, trainer_name, race_distance, race_venue)
            features['draw'] = draw
            features['relative_rating'] = features['current_rating'] - race_avg_rating
            features['draw_dist'] = draw * race_distance
            
            # Calculate score
            score = 0
            for feature, weight in weights.items():
                if feature == 'randomness':
                    # Add random noise (simulates unpredictability factor)
                    import random
                    score += weight * random.uniform(-1, 1) * 5  # -5 to +5 range
                elif feature in features:
                    score += weight * features[feature]
            
            results.append({
                'horse_name': horse_name,
                'jockey': jockey_name,
                'trainer': trainer_name,
                'draw': draw,
                'score': score,
                **features
            })
        
        # Sort by score
        results.sort(key=lambda x: -x['score'])
        
        return {
            'race_id': race_id,
            'predictions': results
        }
    
    def optimize_weights(self, test_race_ids=None, iterations=100):
        """
        Find optimal weights using random search
        
        Args:
            test_race_ids: List of race IDs to test on
            iterations: Number of random combinations to try
            
        Returns:
            Best weights found
        """
        if test_race_ids is None:
            # Use last 20% of races
            unique_races = [r.get('race_id') or r.get('hkjc_race_id') for r in self.races]
            split_idx = int(len(unique_races) * 0.8)
            test_race_ids = unique_races[split_idx:]
        
        feature_names = ['career_place_rate', 'hj_win_rate', 'jockey_win_rate', 
                        'trainer_win_rate', 'dist_win_rate', 'recent3_avg_rank',
                        'current_rating', 'dist_wins', 'jt_win_rate', 'draw']
        
        best_1st = 0
        best_weights = None
        
        print(f"Testing {iterations} weight combinations on {len(test_race_ids)} races...")
        
        for i in range(iterations):
            weights = {f: np.random.uniform(0, 10) for f in feature_names}
            
            correct_1st = 0
            for race_id in test_race_ids:
                result = self.predict_race(race_id, weights)
                if 'error' in result:
                    continue
                
                predicted_winner = result['predictions'][0]['horse_name']
                
                # Get actual winner
                race = None
                for r in self.races:
                    if (r.get('race_id') == race_id or r.get('hkjc_race_id') == race_id):
                        race = r
                        break
                
                if race:
                    for runner in race.get('results', []):
                        try:
                            rank = int(runner.get('rank', 0)) if runner.get('rank') else 0
                        except Exception:
                            rank = 0
                        if rank == 1:
                            if runner.get('horse_name') == predicted_winner:
                                correct_1st += 1
                            break
            
            if correct_1st > best_1st:
                best_1st = correct_1st
                best_weights = weights.copy()
        
        return {
            'weights': best_weights,
            'correct_1st': best_1st,
            'accuracy': best_1st / len(test_race_ids) * 100
        }


# Default weights (based on ML importance)
DEFAULT_WEIGHTS = {
    'hj_win_rate': 10,         # Most important
    'career_place_rate': 5,
    'jockey_win_rate': 3,
    'trainer_win_rate': 2,
    'dist_win_rate': 2,
    'recent3_avg_rank': 2,      # Lower is better, so will be subtracted
    'current_rating': 1,
    'dist_wins': 1,
    'jt_win_rate': 1,
    'draw': -1,                 # Higher draw is usually worse
    'randomness': 3,            # Random factor - adds unpredictability
}


def main():
    """Example usage"""
    scorer = WeightedScorer()
    scorer.load_data()
    
    # Get upcoming races or latest race
    latest_race = scorer.races[-1] if scorer.races else None
    
    if latest_race:
        race_id = latest_race.get('race_id') or latest_race.get('hkjc_race_id')
        print(f"\n=== Predicting Race: {race_id} ===")
        
        result = scorer.predict_race(race_id, DEFAULT_WEIGHTS)
        
        if 'error' not in result:
            print("\nPredicted Order:")
            for i, horse in enumerate(result['predictions'][:5], 1):
                print(f"{i}. {horse['horse_name']:15s} (Score: {horse['score']:.2f})")
                print(f"   Jockey: {horse['jockey']}, Draw: {horse['draw']}")
                print(f"   HJ: {horse['hj_win_rate']:.2f}, CPR: {horse['career_place_rate']:.2f}")


if __name__ == "__main__":
    main()
