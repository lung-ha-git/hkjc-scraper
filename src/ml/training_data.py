"""
Training Data Builder
Builds ML training datasets from historical race data
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from src.ml.features import FeatureEngineer
from src.database.connection import DatabaseConnection as Database
from src.utils import logger


class TrainingDataBuilder:
    """
    Builds training datasets for ML models
    
    Creates:
    - Win prediction dataset (binary classification)
    - Place prediction dataset (binary classification)
    - Rank prediction dataset (regression)
    """
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.feature_engineer = FeatureEngineer(self.db)
    
    def build_win_dataset(
        self, 
        start_date: str, 
        end_date: str,
        min_season_stats: int = 5
    ) -> pd.DataFrame:
        """
        Build dataset for win prediction
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            min_season_stats: Minimum season starts required
            
        Returns:
            DataFrame with features and win label
        """
        logger.info(f"Building win dataset: {start_date} to {end_date}")
        
        # Convert date format for DB query
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_str_db = start_dt.strftime("%Y/%m/%d")
            end_str_db = end_dt.strftime("%Y/%m/%d")
        except:
            start_str_db = start_date
            end_str_db = end_date
        
        # Query races
        races = list(self.db.db["races"].find({
            "$or": [
                {"race_date": {"$gte": start_date, "$lte": end_date}},
                {"race_date": {"$gte": start_str_db, "$lte": end_str_db}},
            ]
        }).sort("race_date", 1))
        
        if not races:
            logger.warning(f"No races found between {start_date} and {end_date}")
            return pd.DataFrame()
        
        logger.info(f"Found {len(races)} races")
        
        all_samples = []
        
        for race in races:
            race_id = race.get("race_id") or race.get("hkjc_race_id", "")
            race_date = race.get("race_date", "")
            race_info = {
                "date": race_date,
                "venue": race.get("venue", ""),
                "race_no": race.get("race_no", 0),
                "distance": race.get("distance", 0),
                "course": race.get("course", "TURF"),
                "track_condition": race.get("track_condition", ""),
                "race_class": race.get("class", ""),
            }
            
            # Get results (not runners)
            results = race.get("results", [])
            
            for runner in results:
                horse_name = runner.get("horse_name", "")
                if not horse_name:
                    continue
                
                # Find horse by name
                horse = self.db.db["horses"].find_one({"name": horse_name})
                if not horse:
                    horse = self.db.db["horses"].find_one({
                        "name": {"$regex": horse_name, "$options": "i"}
                    })
                
                if not horse:
                    continue
                
                horse_id = horse.get("hkjc_horse_id")
                
                # Skip if not enough season stats
                if (horse.get("career_starts", 0) or 0) < min_season_stats:
                    continue
                
                # Get features
                horse_feats = self.feature_engineer.get_horse_features(
                    horse_id, race_date, race_info
                )
                horse_feats["horse_name"] = horse_name
                
                jockey_feats = self.feature_engineer.get_jockey_features(
                    runner.get("jockey", "")
                )
                trainer_feats = self.feature_engineer.get_trainer_features(
                    runner.get("trainer", "")
                )
                matchup_feats = self.feature_engineer.get_matchup_features(
                    horse_id,
                    runner.get("jockey", ""),
                    runner.get("trainer", "")
                )
                
                # Label: 1 if won, 0 otherwise
                rank_str = runner.get("rank") or runner.get("position", "0")
                try:
                    rank = int(rank_str) if rank_str else 0
                except:
                    rank = 0
                
                label = 1 if rank == 1 else 0
                
                # Combine features
                sample = {
                    **horse_feats,
                    **jockey_feats,
                    **matchup_feats,
                    "draw": runner.get("draw", 0),
                    "horse_number": runner.get("horse_number", 0),
                    "win_odds": runner.get("win_odds", 0) or 0,
                    "win": label,
                    "rank": rank,
                    "race_id": race_id,
                    "race_date": race_date,
                }
                
                all_samples.append(sample)
        
        df = pd.DataFrame(all_samples)
        
        if len(df) == 0:
            logger.warning("No samples found")
            return df
            
        logger.info(f"Built dataset with {len(df)} samples, {df['win'].sum()} wins")
        
        return df
    
    def build_place_dataset(
        self,
        start_date: str,
        end_date: str,
        min_season_stats: int = 5
    ) -> pd.DataFrame:
        """
        Build dataset for place (top 3) prediction
        
        Args:
            start_date: Start date
            end_date: End date
            min_season_stats: Minimum season starts
            
        Returns:
            DataFrame with features and place label
        """
        logger.info(f"Building place dataset: {start_date} to {end_date}")
        
        # Convert date format for DB query (DB uses YYYY/MM/DD or YYYY-MM-DD)
        # Try both formats
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            start_str_db = start_dt.strftime("%Y/%m/%d")
            end_str_db = end_dt.strftime("%Y/%m/%d")
        except:
            start_str_db = start_date
            end_str_db = end_date
        
        # Query races - handle both date formats
        races = list(self.db.db["races"].find({
            "$or": [
                {"race_date": {"$gte": start_date, "$lte": end_date}},
                {"race_date": {"$gte": start_str_db, "$lte": end_str_db}},
            ]
        }).sort("race_date", 1))
        
        if not races:
            logger.warning(f"No races found between {start_date} and {end_date}")
            return pd.DataFrame()
        
        logger.info(f"Found {len(races)} races")
        
        all_samples = []
        
        for race in races:
            race_id = race.get("race_id") or race.get("hkjc_race_id", "")
            race_date = race.get("race_date", "")
            race_info = {
                "date": race_date,
                "venue": race.get("venue", ""),
                "race_no": race.get("race_no", 0),
                "distance": race.get("distance", 0),
                "course": race.get("course", "TURF"),
                "track_condition": race.get("track_condition", ""),
                "race_class": race.get("class", ""),
            }
            
            # Get results (not runners)
            results = race.get("results", [])
            
            for runner in results:
                # Try to find horse by name
                horse_name = runner.get("horse_name", "")
                if not horse_name:
                    continue
                
                horse = self.db.db["horses"].find_one({"name": horse_name})
                if not horse:
                    # Try partial match
                    horse = self.db.db["horses"].find_one({
                        "name": {"$regex": horse_name, "$options": "i"}
                    })
                
                if not horse:
                    continue
                
                horse_id = horse.get("hkjc_horse_id")
                
                # Check season stats
                if (horse.get("career_starts", 0) or 0) < min_season_stats:
                    continue
                
                horse_feats = self.feature_engineer.get_horse_features(
                    horse_id, race_date, race_info
                )
                horse_feats["horse_name"] = horse_name
                
                jockey_feats = self.feature_engineer.get_jockey_features(
                    runner.get("jockey", "")
                )
                trainer_feats = self.feature_engineer.get_trainer_features(
                    runner.get("trainer", "")
                )
                matchup_feats = self.feature_engineer.get_matchup_features(
                    horse_id,
                    runner.get("jockey", ""),
                    runner.get("trainer", "")
                )
                
                # Parse rank
                rank_str = runner.get("rank") or runner.get("position", "0")
                try:
                    rank = int(rank_str) if rank_str else 0
                except:
                    rank = 0
                
                label = 1 if rank <= 3 else 0
                
                sample = {
                    **horse_feats,
                    **jockey_feats,
                    **matchup_feats,
                    "draw": runner.get("draw", 0),
                    "horse_number": runner.get("horse_number", 0),
                    "win_odds": runner.get("win_odds", 0) or 0,
                    "place": label,
                    "rank": rank,
                    "race_id": race_id,
                    "race_date": race_date,
                }
                
                all_samples.append(sample)
        
        df = pd.DataFrame(all_samples)
        
        if len(df) == 0:
            logger.warning("No samples found in date range")
            return df
            
        logger.info(f"Built dataset with {len(df)} samples, {df['place'].sum()} places")
        
        return df
    
    def build_race_features_matrix(
        self,
        race_ids: List[str]
    ) -> pd.DataFrame:
        """
        Build feature matrix for upcoming races (for prediction)
        
        Args:
            race_ids: List of race IDs
            
        Returns:
            DataFrame with features for each horse in each race
        """
        logger.info(f"Building feature matrix for {len(race_ids)} races")
        
        all_samples = []
        
        for race_id in race_ids:
            features = self.feature_engineer.build_race_features(race_id)
            
            if not features:
                continue
            
            race_info = features.get("race_info", {})
            horses = features.get("horses", [])
            
            for horse in horses:
                sample = {
                    "race_id": race_id,
                    "race_date": race_info.get("race_date", ""),
                    "venue": race_info.get("venue", ""),
                    "distance": race_info.get("distance", 0),
                    **horse,
                }
                all_samples.append(sample)
        
        df = pd.DataFrame(all_samples)
        logger.info(f"Built feature matrix with {len(df)} horse entries")
        
        return df
    
    def split_train_test(
        self,
        df: pd.DataFrame,
        test_size: float = 0.2,
        date_split: Optional[str] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split dataset into train and test
        
        Args:
            df: Full dataset
            test_size: Fraction for test (if not using date_split)
            date_split: Optional date to split on (train before, test after)
            
        Returns:
            (train_df, test_df)
        """
        if date_split:
            train_df = df[df["race_date"] < date_split]
            test_df = df[df["race_date"] >= date_split]
        else:
            split_idx = int(len(df) * (1 - test_size))
            train_df = df.iloc[:split_idx]
            test_df = df.iloc[split_idx:]
        
        logger.info(f"Split: train={len(train_df)}, test={len(test_df)}")
        
        return train_df, test_df
    
    def save_dataset(self, df: pd.DataFrame, filename: str):
        """Save dataset to CSV"""
        path = f"/Users/fatlung/.openclaw/workspace-main/hkjc_project/data/{filename}"
        df.to_csv(path, index=False)
        logger.info(f"Saved dataset to {path}")


if __name__ == "__main__":
    # Test
    builder = TrainingDataBuilder()
    
    # Example: Build win dataset for 2025 season
    # df = builder.build_win_dataset("2025-01-01", "2025-12-31")
    # print(df.head())
    # print(f"Columns: {df.columns.tolist()}")
    
    print("TrainingDataBuilder initialized")
