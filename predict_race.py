#!/usr/bin/env python3
"""
Simple prediction API endpoint
"""
import sys
import os
import json

# Suppress logging before importing
os.environ['PYTHONUNBUFFERED'] = '1'
os.environ['LOG_LEVEL'] = 'ERROR'

# Suppress print statements from imports
import io
from contextlib import redirect_stdout, suppress

# First import and setup logging, then load scorer
sys.path.insert(0, '/Users/fatlung/.openclaw/workspace-main/hkjc_project')

# Suppress any logging
import logging
logging.getLogger().setLevel(logging.CRITICAL)

from src.ml.weighted_scorer import WeightedScorer, DEFAULT_WEIGHTS


def predict(entries, distance, venue):
    """Predict race results"""
    scorer = WeightedScorer()
    scorer.load_data()
    
    predictions = []
    for entry in entries:
        features = scorer.get_horse_features(
            entry['horse_name'], 
            entry['jockey_name'], 
            entry['trainer_name'],
            distance,
            venue
        )
        features['draw'] = entry.get('draw', 0)
        features['relative_rating'] = features.get('current_rating', 0)
        features['draw_dist'] = entry.get('draw', 0) * distance
        
        score = 0
        for feature, weight in DEFAULT_WEIGHTS.items():
            if feature in features:
                score += weight * features[feature]
        
        predictions.append({
            'horse_name': entry['horse_name'],
            'jockey': entry['jockey_name'],
            'trainer': entry['trainer_name'],
            'draw': entry.get('draw', 0),
            'score': score,
            **features
        })
    
    predictions.sort(key=lambda x: -x['score'])
    for i, p in enumerate(predictions):
        p['predicted_rank'] = i + 1
    
    return predictions


if __name__ == "__main__":
    # Read from stdin
    data = json.load(sys.stdin)
    entries = data.get('entries', [])
    distance = data.get('distance', 1200)
    venue = data.get('venue', 'ST')
    
    predictions = predict(entries, distance, venue)
    # Print ONLY JSON
    sys.stdout.write(json.dumps({"predictions": predictions}, ensure_ascii=False))
