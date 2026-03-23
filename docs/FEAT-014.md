# FEAT-014: ML Model Enhancement — Advanced Prediction Features

## Overview

**Status**: ✅ COMPLETED (2026-03-24)  
**Priority**: HIGH  
**Estimated Time**: 2-3 days  
**Completed**: 2026-03-24  
**Final Accuracy**: **67.4%** (Top-4) | **68.5%** (Win Model)  
**Target**: >60% ✅ **EXCEEDED**

## Results Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Top-4 Accuracy | 56.7% | **67.4%** | +10.7% |
| Win Model Top-4 | - | **68.5%** | - |
| Prediction Uncertainty | - | **0.0416** | Lower = better |
| Features | 23 | **47** | +24 new features |
| Base Models | 1 (XGBoost) | **3** (XGBoost + LightGBM + MLP) |

## Implementation Files

```
hkjc_project/
├── src/ml/
│   ├── enhanced_predictor.py      ✅ FEAT-014.1-14.11 Complete
│   └── features/feature_engineer.py  ✅ Extended
├── train_ensemble.py              ✅ Training script
├── predict_enhanced.py            ✅ Prediction script
└── models/
    ├── ensemble_v1_win.pkl        ✅ Win model
    ├── ensemble_v1_top4.pkl       ✅ Top-4 model
    └── ensemble_v1_config.json    ✅ Config
```

## Phase 1: Advanced Feature Engineering ✅

### 14.1 Odds-Based Features ✅
- `odds_drift`: (current - opening) / opening
- `odds_volatility`: std of odds history
- `market_confidence`: 1 / sum(all win odds)
- `odds_trend`: slope of odds over time
- `odds_compression`: normalized position in odds range

## Current Model Analysis

### Existing XGBoost Model
- **Features**: 23 base features
- **Model**: Single XGBoost Classifier
- **Accuracy**: 56.7% (top-4 prediction)
- **ROI**: ~-92% (expected loss due to bookmaker margin)

### Identified Limitations
1. **Single Model**: No ensemble, limited robustness
2. **Static Features**: No real-time odds integration
3. **Simple Confidence**: Binary scoring without calibration
4. **Limited Feature Engineering**: Missing pace, track condition analysis

## Enhancement Plan

### Phase 1: Advanced Feature Engineering

#### 14.1 Odds-Based Features ⭐ High Impact
```python
odds_drift = (current_odds - opening_odds) / opening_odds
odds_volatility = std(odds_history_last_30min)
market_confidence = 1 / sum(all_horses_win_odds)  # Bookmaker margin
odds_trend = slope(odds_history)  # Improving or drifting
```
**Why**: Market movements contain information about insider knowledge

#### 14.2 Pace Analysis Features ⭐ High Impact
```python
early_pace = average(position_at_first_400m)
closing_ability = average(final_400m_position_change)
pace_figure = early_pace - closing_ability
pace_match = compatibility_with_race_pace_profile
```
**Why**: Pace scenarios heavily influence race outcomes

#### 14.3 Track Condition Features ⭐ Medium Impact
```python
wet_performance = wins_on_wet / runs_on_wet
dry_performance = wins_on_dry / runs_on_dry
condition_advantage = wet_performance - dry_performance
```
**Why**: Some horses perform significantly better on specific track conditions

#### 14.4 Class Level Features ⭐ Medium Impact
```python
same_class_win_rate = wins_in_same_class / runs_in_same_class
class_rating_trend = current_rating - avg_rating_last_3_races
class_transition = indicator(up/down/same class)
```
**Why**: Class drops often indicate winning opportunities

### Phase 2: Ensemble Model Architecture

```
                    Raw Features (50+ features)
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  XGBoost   │  │  LightGBM  │  │   Neural   │
    │  (trees)   │  │  (trees)   │  │   Network  │
    └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
          │               │               │
          └───────────────┼───────────────┘
                          │
                          ▼
                   ┌────────────┐
                   │  Stacker   │  (Meta-learner: LR/XGB)
                   │  (Blender) │
                   └─────┬──────┘
                          │
                          ▼
              Final Probability + Confidence
```

**Models**:
- XGBoost: Handles non-linear interactions well
- LightGBM: Faster training, leaf-wise growth
- Neural Network: Captures complex patterns

### Phase 3: Confidence Calibration

#### 14.9 Probability Calibration
- **Platt Scaling**: Logistic regression on raw scores
- **Isotonic Regression**: Non-parametric calibration
- **Temperature Scaling**: Neural network approach

#### 14.10 Uncertainty Quantification
- **MC Dropout**: Multiple forward passes with dropout
- **Conformal Prediction**: Prediction intervals with coverage guarantees
- **Ensemble Variance**: Disagreement between base models

#### 14.11 Dynamic Confidence
```python
if ensemble_variance < threshold and all_models_agree:
    confidence = "HIGH"
elif model_consensus > 0.7:
    confidence = "MEDIUM"
else:
    confidence = "LOW"
```

## New Features Summary

| Category | Count | Key Features |
|----------|-------|--------------|
| Base (existing) | 23 | rating, career stats, distance, jockey-trainer |
| Odds-based | 4 | drift, volatility, trend, market confidence |
| Pace | 3 | early pace, closing ability, pace figure |
| Track Condition | 3 | wet/dry performance, condition advantage |
| Class Level | 3 | same class win rate, rating trend, transition |
| **Total** | **36** | Enhanced feature set |

## Expected Improvements

| Metric | Current | Target | Improvement |
|--------|---------|--------|-------------|
| Top-4 Accuracy | 56.7% | 60%+ | +3.3% |
| ROI | -92% | -10% | +82% |
| Confidence Calibration | Poor | Good | Brier <0.2 |
| Prediction Stability | Medium | High | Less variance |

## Implementation Files

```
hkjc_project/
├── src/ml/
│   ├── enhanced_predictor.py      # Main predictor
│   ├── feature_engineering.py     # FEAT-014.1-14.4
│   ├── ensemble_trainer.py        # FEAT-014.5-14.8
│   ├── calibrator.py              # FEAT-014.9-14.11
│   └── backtester.py              # FEAT-014.12
├── models/
│   ├── ensemble_v1.pkl            # Trained ensemble
│   └── calibration_params.pkl     # Calibration parameters
└── notebooks/
    └── model_analysis.ipynb       # Performance analysis
```

## Usage Examples

```python
from src.ml.enhanced_predictor import EnhancedPredictor

# Initialize
predictor = EnhancedPredictor()

# Predict with confidence
result = predictor.predict(
    date='2026-03-25',
    venue='HV',
    race_no=1
)

# Output format
{
    'predictions': [
        {
            'horse_no': 1,
            'horse_name': '富喜來',
            'probability': 0.245,
            'ensemble_std': 0.023,      # Uncertainty
            'confidence': 'HIGH',        # Calibrated confidence
            'top4_probability': 0.67,
            'features': {...}            # SHAP values for interpretability
        }
    ],
    'race_confidence': 72,            # Overall race confidence
    'model_agreement': 0.89,          # Ensemble consensus
    'backtested_roi': -0.05           # Historical performance
}
```

## Testing Strategy

1. **Time-Series Cross-Validation**: Respect temporal order
2. **Walk-Forward Testing**: Train on past, test on future
3. **Bootstrap Confidence Intervals**: Statistical significance
4. **Paper Trading**: Validate before real deployment

## Next Steps

~~1. Implement feature engineering pipeline~~ ✅ DONE
~~2. Train base models with hyperparameter tuning~~ ✅ DONE
~~3. Build stacking ensemble~~ ✅ DONE
~~4. Calibrate probabilities~~ ✅ DONE
~~5. Backtest and validate~~ ✅ DONE

---

## Training Results (2026-03-24)

```
Training Data:
- Period: 365 days
- Total races: 515
- Total samples: 8,006
- Training set: 6,404
- Validation set: 1,602

Models Trained:
- XGBoost: n_estimators=200, max_depth=6, lr=0.05
- LightGBM: n_estimators=200, max_depth=6, lr=0.05
- Neural Network: (128, 64, 32) hidden layers
- Stacker: Logistic Regression meta-learner

Performance:
- Win Model Top-4 Accuracy: 68.5%
- Top-4 Model Accuracy: 67.4%
- Average Ensemble Std: 0.0416 (lower = more confident)
```

## Usage

```bash
# Train new models
python train_ensemble.py --days 365 --output models/ensemble_v1.pkl

# Make predictions
python predict_enhanced.py --date 2026-03-25 --venue HV --race 1
python predict_enhanced.py --race-id 2026-03-25_HV_R1
```

## Files Created

| File | Description |
|------|-------------|
| `src/ml/enhanced_predictor.py` | Core classes: EnhancedFeatureEngineer, EnsembleTrainer, ProbabilityCalibrator |
| `train_ensemble.py` | Training pipeline with walk-forward validation |
| `predict_enhanced.py` | Prediction script with confidence levels |
| `models/ensemble_v1_*.pkl` | Trained model files |
| `models/ensemble_v1_config.json` | Feature columns and metadata |
