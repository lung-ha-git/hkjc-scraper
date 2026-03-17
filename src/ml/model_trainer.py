"""
ML Model Trainer for HKJC Racing Prediction
 Trains XGBoost models for win/place prediction
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, 
    roc_auc_score, classification_report, confusion_matrix
)
from sklearn.preprocessing import StandardScaler, LabelEncoder
import warnings
warnings.filterwarnings('ignore')

# Try to import XGBoost, fall back to sklearn if not available
try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False
    print("XGBoost not available, using sklearn GradientBoosting")

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
except ImportError:
    pass

from src.ml.training_data import TrainingDataBuilder
from src.database.connection import DatabaseConnection
from src.utils import logger


class ModelTrainer:
    """
    Train ML models for HKJC racing predictions
    
    Supports:
    - Win prediction (binary classification)
    - Place prediction (binary classification)
    """
    
    def __init__(self):
        self.db = DatabaseConnection()
        self.db.connect()
        self.builder = TrainingDataBuilder(self.db)
        self.scaler = StandardScaler()
        self.label_encoders = {}
        
    def prepare_features(self, df: pd.DataFrame, target_col: str = "place") -> Tuple:
        """
        Prepare features for training
        
        Args:
            df: Training DataFrame
            target_col: Target column name
            
        Returns:
            (X, y, feature_names)
        """
        # Define feature columns to use
        numeric_features = [
            # Horse features
            "age", "current_rating", "rating_change",
            "career_starts", "career_wins", "career_seconds", "career_thirds",
            "career_win_rate", "career_place_rate",
            "season_prize", "total_prize",
            "distance_wins", "distance_runs", "distance_win_rate", "distance_place_rate",
            "track_wins", "track_runs", "track_win_rate",
            "recent_races", "recent_wins", "recent_places", "recent_avg_rank", "recent_win_rate",
            "days_since_last",
            
            # Jockey features
            "wins", "total_rides", "win_rate", "place_rate", "prize_money",
            
            # Trainer features
            "total_races", "place_rate",
            
            # Matchup features
            "horse_jockey_races", "horse_jockey_wins", "horse_jockey_win_rate",
            "horse_trainer_races", "horse_trainer_wins", "horse_trainer_win_rate",
            
            # Race features
            "draw", "horse_number", "win_odds",
            "distance", "total_runners",
        ]
        
        # Filter to existing columns
        feature_cols = [c for c in numeric_features if c in df.columns]
        
        # Add encoded categorical features
        categorical_features = ["sex", "country", "import_type", "venue"]
        for cat in categorical_features:
            if cat in df.columns:
                # Encode
                if cat not in self.label_encoders:
                    self.label_encoders[cat] = LabelEncoder()
                    df[f"{cat}_encoded"] = self.label_encoders[cat].fit_transform(
                        df[cat].fillna("Unknown").astype(str)
                    )
                else:
                    df[f"{cat}_encoded"] = self.label_encoders[cat].transform(
                        df[cat].fillna("Unknown").astype(str)
                    )
                feature_cols.append(f"{cat}_encoded")
        
        X = df[feature_cols].copy()
        y = df[target_col].copy()
        
        # Fill missing values
        X = X.fillna(0)
        
        # Replace infinities
        X = X.replace([np.inf, -np.inf], 0)
        
        logger.info(f"Using {len(feature_cols)} features: {feature_cols}")
        
        return X, y, feature_cols
    
    def train_xgboost(
        self, 
        X_train: pd.DataFrame, 
        y_train: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series,
        objective: str = "binary:logistic"
    ) -> Tuple:
        """
        Train XGBoost model
        """
        if not HAS_XGBOOST:
            logger.warning("XGBoost not available, using GradientBoosting")
            model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
            model.fit(X_train, y_train)
            return model, None
        
        # XGBoost parameters
        params = {
            "objective": objective,
            "max_depth": 5,
            "learning_rate": 0.1,
            "n_estimators": 100,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "random_state": 42,
            "use_label_encoder": False,
            "eval_metric": "logloss"
        }
        
        model = xgb.XGBClassifier(**params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False
        )
        
        return model, model.get_booster()
    
    def train_random_forest(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series
    ):
        """Train Random Forest model"""
        model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)
        return model
    
    def evaluate_model(
        self, 
        model, 
        X_test: pd.DataFrame, 
        y_test: pd.Series,
        model_name: str = "Model"
    ) -> Dict:
        """
        Evaluate model performance
        """
        y_pred = model.predict(X_test)
        
        # Get probability scores if available
        try:
            y_prob = model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, y_prob)
        except (AttributeError, ValueError):
            y_prob = None
            auc = 0
        
        results = {
            "model": model_name,
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred, zero_division=0),
            "recall": recall_score(y_test, y_pred, zero_division=0),
            "auc": auc,
            "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        }
        
        logger.info(f"\n{'='*50}")
        logger.info(f"{model_name} Results:")
        logger.info(f"{'='*50}")
        logger.info(f"Accuracy:  {results['accuracy']:.3f}")
        logger.info(f"Precision: {results['precision']:.3f}")
        logger.info(f"Recall:    {results['recall']:.3f}")
        logger.info(f"AUC:       {results['auc']:.3f}")
        logger.info(f"\nConfusion Matrix:")
        logger.info(f"{results['confusion_matrix']}")
        
        return results
    
    def train_place_model(
        self,
        start_date: str = "2025-01-01",
        end_date: str = "2026-03-01",
        test_size: float = 0.2,
        model_type: str = "xgboost"
    ) -> Tuple:
        """
        Train place (top 3) prediction model
        
        Args:
            start_date: Training data start date
            end_date: Training data end date
            test_size: Fraction for test set
            model_type: "xgboost" or "random_forest"
            
        Returns:
            (model, results)
        """
        logger.info(f"\n{'='*60}")
        logger.info("Training Place Prediction Model")
        logger.info(f"{'='*60}")
        
        # Build dataset
        logger.info(f"Building dataset: {start_date} to {end_date}")
        df = self.builder.build_place_dataset(start_date, end_date, min_season_stats=1)
        
        if len(df) == 0:
            logger.error("No data available for training")
            return None, {}
        
        logger.info(f"Dataset: {len(df)} samples, {df['place'].sum()} positive (places)")
        
        # Prepare features
        X, y, feature_names = self.prepare_features(df, target_col="place")
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=test_size, random_state=42, stratify=y
        )
        
        logger.info(f"Train: {len(X_train)}, Test: {len(X_test)}")
        
        # Train model
        if model_type == "xgboost":
            model, booster = self.train_xgboost(
                X_train, y_train, X_test, y_test
            )
        else:
            model = self.train_random_forest(X_train, y_train)
            booster = None
        
        # Evaluate
        results = self.evaluate_model(model, X_test, y_test, f"{model_type} Place")
        
        # Feature importance
        if hasattr(model, 'feature_importances_'):
            importance = pd.DataFrame({
                "feature": feature_names,
                "importance": model.feature_importances_
            }).sort_values("importance", ascending=False)
            
            logger.info(f"\nTop 10 Features:")
            for i, row in importance.head(10).iterrows():
                logger.info(f"  {row['feature']}: {row['importance']:.4f}")
            
            results["feature_importance"] = importance.to_dict()
        
        return model, results
    
    def train_win_model(
        self,
        start_date: str = "2025-01-01",
        end_date: str = "2026-03-01",
        test_size: float = 0.2
    ) -> Tuple:
        """
        Train win prediction model
        """
        logger.info(f"\n{'='*60}")
        logger.info("Training Win Prediction Model")
        logger.info(f"{'='*60}")
        
        # Build dataset
        df = self.builder.build_win_dataset(start_date, end_date, min_season_stats=1)
        
        if len(df) == 0:
            logger.error("No data available for training")
            return None, {}
        
        logger.info(f"Dataset: {len(df)} samples, {df['win'].sum()} wins")
        
        # Prepare features
        X, y, feature_names = self.prepare_features(df, target_col="win")
        
        # Scale
        X_scaled = self.scaler.fit_transform(X)
        
        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Train
        model, booster = self.train_xgboost(X_train, y_train, X_test, y_test)
        
        # Evaluate
        results = self.evaluate_model(model, X_test, y_test, "XGBoost Win")
        
        return model, results
    
    def cross_validate(
        self,
        model,
        X: pd.DataFrame,
        y: pd.Series,
        cv: int = 5
    ) -> Dict:
        """
        Perform cross-validation
        """
        X_scaled = self.scaler.fit_transform(X.fillna(0))
        
        scores = cross_val_score(model, X_scaled, y, cv=cv, scoring='roc_auc')
        
        logger.info(f"\nCross-Validation ({cv} folds):")
        logger.info(f"  AUC: {scores.mean():.3f} (+/- {scores.std()*2:.3f})")
        
        return {
            "cv_scores": scores.tolist(),
            "cv_mean": scores.mean(),
            "cv_std": scores.std()
        }


def main():
    """Main training script"""
    print("\n" + "="*60)
    print("HKJC Racing ML Model Training")
    print("="*60 + "\n")
    
    trainer = ModelTrainer()
    
    # Train Place Model (predict top 3)
    logger.info("Training Place Model...")
    place_model, place_results = trainer.train_place_model(
        start_date="2025-01-01",
        end_date="2026-03-01",
        model_type="xgboost"
    )
    
    # Train Win Model
    logger.info("\nTraining Win Model...")
    win_model, win_results = trainer.train_win_model(
        start_date="2025-01-01",
        end_date="2026-03-01"
    )
    
    print("\n" + "="*60)
    print("Training Complete!")
    print("="*60)
    print(f"\nPlace Model Accuracy: {place_results.get('accuracy', 0):.3f}")
    print(f"Win Model Accuracy: {win_results.get('accuracy', 0):.3f}")
    
    return place_model, win_model, place_results, win_results


if __name__ == "__main__":
    main()
