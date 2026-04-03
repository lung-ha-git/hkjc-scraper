#!/usr/bin/env python3
"""FEAT-014: Enhanced ML Predictor"""
import sys, os, json, pickle, argparse, numpy as np, warnings
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional
sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')
from src.database.connection import DatabaseConnection
from src.ml.features.feature_engineer import FeatureEngineer
warnings.filterwarnings('ignore')

class EnhancedFeatureEngineer(FeatureEngineer):
    """FEAT-014.1-14.4: Advanced feature engineering"""
    
    def __init__(self, db=None):
        super().__init__(db)
        self.live_odds_cache = {}
        self.horse_detailed_history = defaultdict(list)
        self._load_live_odds_data()
        self._load_horse_history_detailed()
    
    def _load_live_odds_data(self):
        try:
            odds_data = list(self.db.db['live_odds'].find().sort('timestamp', -1))
            for od in odds_data:
                race_key = f"{od.get('race_id')}"
                if race_key not in self.live_odds_cache:
                    self.live_odds_cache[race_key] = []
                self.live_odds_cache[race_key].append(od)
            print(f"[features] Loaded {len(odds_data)} live odds records")
        except Exception as e:
            print(f"[features] No live odds data: {e}")
    
    def _load_horse_history_detailed(self):
        history = list(self.db.db['horse_race_history'].find({}))
        for h in history:
            horse_id = h.get('hkjc_horse_id')
            if horse_id:
                self.horse_detailed_history[horse_id].append(h)
        print(f"[features] Loaded detailed history for {len(self.horse_detailed_history)} horses")
    
    def get_odds_based_features(self, horse_no: int, race_id: str) -> Dict:
        features = {'odds_drift': 0.0, 'odds_volatility': 0.0, 'market_confidence': 0.0, 
                    'odds_trend': 0.0, 'odds_compression': 0.0}
        odds_history = self.live_odds_cache.get(race_id, [])
        if not odds_history:
            return features
        
        horse_odds_history = []
        for snap in odds_history:
            data = snap.get('data', {})
            for horse_key, odds in data.items():
                try:
                    if int(horse_key) == horse_no or str(horse_key) == str(horse_no):
                        win_odds = odds.get('win', 0) if isinstance(odds, dict) else odds
                        if win_odds and float(win_odds) > 0:
                            horse_odds_history.append({'timestamp': snap.get('timestamp'), 'win_odds': float(win_odds)})
                except (ValueError, TypeError):
                    continue
        
        if len(horse_odds_history) >= 2:
            horse_odds_history.sort(key=lambda x: x['timestamp'])
            odds_values = [o['win_odds'] for o in horse_odds_history]
            opening, current = odds_values[0], odds_values[-1]
            if opening > 0:
                features['odds_drift'] = (current - opening) / opening
            if len(odds_values) >= 3:
                features['odds_volatility'] = np.std(odds_values)
                x = np.arange(len(odds_values))
                features['odds_trend'] = np.polyfit(x, odds_values, 1)[0]
            min_odds, max_odds = min(odds_values), max(odds_values)
            if max_odds > min_odds:
                features['odds_compression'] = (current - min_odds) / (max_odds - min_odds)
        
        if odds_history:
            latest = odds_history[-1]
            data = latest.get('data', {})
            total_prob = sum(1/float(o.get('win', o) if isinstance(o, dict) else o) 
                           for o in data.values() if o and float(o.get('win', o) if isinstance(o, dict) else o) > 0)
            if total_prob > 0:
                features['market_confidence'] = 1 / total_prob
        return features
    
    def get_pace_features(self, horse_id: str) -> Dict:
        features = {'early_pace': 7.0, 'closing_ability': 0.0, 'pace_figure': 7.0,
                    'pace_consistency': 1.0, 'is_front_runner': 0, 'is_closer': 0, 'is_stalker': 0}
        history = self.horse_detailed_history.get(horse_id, [])
        if len(history) < 2:
            return features
        pace_data = []
        for h in history:
            running_pos = h.get('running_position', '')
            if running_pos:
                try:
                    positions = [int(p) for p in str(running_pos).split() if p.strip().isdigit()]
                    if len(positions) >= 2:
                        pace_data.append({'early': positions[0], 'final': positions[-1], 'closing': positions[-1] - positions[0]})
                except (ValueError, TypeError):
                    continue
        if pace_data:
            early_positions = [p['early'] for p in pace_data]
            closing_moves = [p['closing'] for p in pace_data]
            features['early_pace'] = np.mean(early_positions)
            features['closing_ability'] = -np.mean(closing_moves)
            features['pace_figure'] = features['early_pace'] - features['closing_ability']
            features['pace_consistency'] = np.std(early_positions) if len(early_positions) > 1 else 1.0
            features['is_front_runner'] = 1 if features['early_pace'] <= 3.5 else 0
            features['is_closer'] = 1 if features['early_pace'] >= 7 else 0
            features['is_stalker'] = 1 if 3.5 < features['early_pace'] < 7 else 0
        return features
    
    def get_track_condition_features(self, horse_id: str, current_condition: str = None) -> Dict:
        features = {'wet_wins': 0, 'wet_runs': 0, 'wet_win_rate': 0.0, 'dry_wins': 0, 'dry_runs': 0,
                    'dry_win_rate': 0.0, 'condition_advantage': 0.0, 'condition_match': 0}
        history = self.horse_detailed_history.get(horse_id, [])
        wet_conditions = ['WET', 'SOFT', 'HEAVY', '濕', '軟', '爛地']
        dry_conditions = ['GOOD', 'FIRM', '乾', '好地']
        for h in history:
            condition = str(h.get('track_condition', ''))
            position = self._parse_position(h.get('position', 0))
            is_wet = any(wc in condition.upper() for wc in wet_conditions)
            is_dry = any(dc in condition.upper() for dc in dry_conditions)
            if is_wet:
                features['wet_runs'] += 1
                if position == 1: features['wet_wins'] += 1
            elif is_dry:
                features['dry_runs'] += 1
                if position == 1: features['dry_wins'] += 1
        if features['wet_runs'] > 0: features['wet_win_rate'] = features['wet_wins'] / features['wet_runs']
        if features['dry_runs'] > 0: features['dry_win_rate'] = features['dry_wins'] / features['dry_runs']
        features['condition_advantage'] = features['wet_win_rate'] - features['dry_win_rate']
        if current_condition:
            current_is_wet = any(wc in str(current_condition).upper() for wc in wet_conditions)
            features['condition_match'] = 1 if (current_is_wet and features['wet_win_rate'] > features['dry_win_rate']) or \
                                              (not current_is_wet and features['dry_win_rate'] > features['wet_win_rate']) else 0
        return features
    
    def get_class_level_features(self, horse_id: str, current_class: str = None, current_rating: int = None) -> Dict:
        import re
        features = {'same_class_runs': 0, 'same_class_wins': 0, 'same_class_win_rate': 0.0,
                    'class_rating_trend': 0.0, 'class_transition': 0, 'class_stability': 0.0, 'avg_class_level': 0.0}
        history = self.horse_detailed_history.get(horse_id, [])
        def extract_class_level(s):
            m = re.search(r'(\d+)', str(s))
            return int(m.group(1)) if m else 0
        current_class_level = extract_class_level(current_class)
        same_class_races = [self._parse_position(h.get('position', 0)) for h in history 
                           if extract_class_level(h.get('race_class', h.get('class', ''))) == current_class_level and current_class_level > 0]
        if same_class_races:
            features['same_class_runs'] = len(same_class_races)
            features['same_class_wins'] = sum(1 for p in same_class_races if p == 1)
            features['same_class_win_rate'] = features['same_class_wins'] / len(same_class_races)
        recent_ratings = [int(h.get('race_rating', 0)) for h in history[:3] if h.get('race_rating')]
        if recent_ratings and current_rating:
            features['class_rating_trend'] = current_rating - np.mean(recent_ratings)
        if history:
            last_class = extract_class_level(history[0].get('race_class', history[0].get('class', '')))
            if current_class_level and last_class:
                features['class_transition'] = 1 if current_class_level > last_class else (-1 if current_class_level < last_class else 0)
        all_class_levels = [extract_class_level(h.get('race_class', h.get('class', ''))) for h in history if extract_class_level(h.get('race_class', h.get('class', ''))) > 0]
        if all_class_levels:
            features['avg_class_level'] = np.mean(all_class_levels)
            if len(all_class_levels) > 1:
                features['class_stability'] = 1 / (1 + np.std(all_class_levels))
        return features
    
    def build_enhanced_race_features(self, race_id: str, include_odds: bool = True) -> Dict:
        """Build complete enhanced feature set for a race with all FEAT-014 features"""
        base_features = self.build_race_features(race_id)
        if not base_features:
            return {}
        
        race_info = base_features.get('race_info', {})
        current_condition = race_info.get('track_condition', '')
        current_class = race_info.get('race_class', '')
        
        for horse_features in base_features.get('horses', []):
            horse_id = horse_features.get('horse_id', '')
            horse_no = horse_features.get('horse_number', 0)
            current_rating = horse_features.get('current_rating', 0)
            
            horse_features['odds_features'] = self.get_odds_based_features(horse_no, race_id) if include_odds else {}
            horse_features['pace_features'] = self.get_pace_features(horse_id)
            horse_features['condition_features'] = self.get_track_condition_features(horse_id, current_condition)
            horse_features['class_features'] = self.get_class_level_features(horse_id, current_class, current_rating)
        
        return base_features


class EnsembleTrainer:
    """FEAT-014.5-14.8: Ensemble with XGBoost + LightGBM + Neural Network"""
    
    def __init__(self, model_dir='models'):
        self.model_dir = model_dir
        self.models = {}
        self.stacker = None
        os.makedirs(model_dir, exist_ok=True)
    
    def train(self, X_train, y_train, X_val=None, y_val=None):
        print("[ensemble] Training base models...")
        try:
            import xgboost as xgb
            self.models['xgb'] = xgb.XGBClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42)
            self.models['xgb'].fit(X_train, y_train, eval_set=[(X_val, y_val)] if X_val is not None else None, verbose=False)
            print("[ensemble] XGBoost trained")
        except Exception as e:
            print(f"[ensemble] XGBoost error: {e}")
        try:
            import lightgbm as lgb
            self.models['lgb'] = lgb.LGBMClassifier(n_estimators=200, max_depth=6, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1)
            self.models['lgb'].fit(X_train, y_train, eval_set=[(X_val, y_val)] if X_val is not None else None)
            print("[ensemble] LightGBM trained")
        except Exception as e:
            print(f"[ensemble] LightGBM error: {e}")
        try:
            from sklearn.neural_network import MLPClassifier
            self.models['mlp'] = MLPClassifier(hidden_layer_sizes=(128, 64, 32), max_iter=500,
                early_stopping=True, validation_fraction=0.1, random_state=42)
            self.models['mlp'].fit(X_train, y_train)
            print("[ensemble] Neural Network trained")
        except Exception as e:
            print(f"[ensemble] Neural Network error: {e}")
        if X_val is not None and len(self.models) >= 2:
            predictions = np.column_stack([model.predict_proba(X_val)[:, 1] for model in self.models.values()])
            from sklearn.linear_model import LogisticRegression
            self.stacker = LogisticRegression(random_state=42)
            self.stacker.fit(predictions, y_val)
            print("[ensemble] Stacker trained")
    
    def predict_proba(self, X):
        if not self.models:
            return None
        predictions = np.column_stack([model.predict_proba(X)[:, 1] for model in self.models.values()])
        return self.stacker.predict_proba(predictions)[:, 1] if self.stacker else np.mean(predictions, axis=1)
    
    def predict(self, X):
        proba = self.predict_proba(X)
        return (proba >= 0.5).astype(int) if proba is not None else None
    
    def get_uncertainty(self, X):
        if len(self.models) < 2:
            return np.zeros(len(X))
        predictions = np.column_stack([model.predict_proba(X)[:, 1] for model in self.models.values()])
        return np.std(predictions, axis=1)
    
    def save(self, name='ensemble_v1'):
        path = os.path.join(self.model_dir, f'{name}.pkl')
        with open(path, 'wb') as f:
            pickle.dump({'models': self.models, 'stacker': self.stacker}, f)
        print(f"[ensemble] Saved to {path}")
    
    def load(self, name='ensemble_v1'):
        path = os.path.join(self.model_dir, f'{name}.pkl')
        with open(path, 'rb') as f:
            data = pickle.load(f)
            self.models = data['models']
            self.stacker = data['stacker']
        print(f"[ensemble] Loaded from {path}")


class ProbabilityCalibrator:
    """FEAT-014.9-14.11: Probability Calibration"""
    
    def __init__(self, method='isotonic'):
        self.method = method
        self.calibrator = None
    
    def fit(self, y_true, y_prob):
        if self.method == 'isotonic':
            from sklearn.isotonic import IsotonicRegression
            self.calibrator = IsotonicRegression(out_of_bounds='clip')
            self.calibrator.fit(y_prob, y_true)
        else:
            from sklearn.linear_model import LogisticRegression
            self.calibrator = LogisticRegression()
            self.calibrator.fit(y_prob.reshape(-1, 1), y_true)
        print(f"[calibrator] Fitted {self.method} calibrator")
    
    def calibrate(self, y_prob):
        if self.calibrator is None:
            return y_prob
        return self.calibrator.predict(y_prob) if self.method == 'isotonic' else self.calibrator.predict_proba(y_prob.reshape(-1, 1))[:, 1]


if __name__ == '__main__':
    print("FEAT-014: Enhanced ML Predictor")
    print("Components: EnhancedFeatureEngineer, EnsembleTrainer, ProbabilityCalibrator")
