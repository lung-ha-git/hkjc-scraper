#!/usr/bin/env python3
"""
Test script for ML Feature Engineering
"""

import sys
sys.path.insert(0, "/Users/fatlung/.openclaw/workspace-main/hkjc_project")

from src.ml import FeatureEngineer, TrainingDataBuilder
from src.database.connection import DatabaseConnection


def test_feature_engineer():
    """Test FeatureEngineer with real data"""
    print("=" * 60)
    print("Testing FeatureEngineer")
    print("=" * 60)
    
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return
    
    engineer = FeatureEngineer(db)
    
    # Test: Get a horse from DB
    horse = db.db["horses"].find_one({})
    
    if not horse:
        print("❌ No horses found in database")
        return
    
    horse_id = horse.get("hkjc_horse_id")
    print(f"Testing with horse: {horse_id} - {horse.get('name')}")
    
    # Get features
    race_info = {
        "distance": 1200,
        "course": "TURF",
    }
    
    features = engineer.get_horse_features(horse_id, "2026-03-15", race_info)
    
    print("\n📊 Horse Features:")
    for key, value in list(features.items())[:15]:
        print(f"  {key}: {value}")
    
    print(f"\n✅ Got {len(features)} features")
    
    # Test jockey features
    if features.get("jockey_name"):
        jockey_feats = engineer.get_jockey_features(features["jockey_name"])
        print(f"\n📊 Jockey ({features['jockey_name']}) Features:")
        print(f"  win_rate: {jockey_feats.get('win_rate', 0):.3f}")
        print(f"  total_rides: {jockey_feats.get('total_rides', 0)}")
    
    # Test trainer features
    if features.get("trainer_name"):
        trainer_feats = engineer.get_trainer_features(features["trainer_name"])
        print(f"\n📊 Trainer ({features['trainer_name']}) Features:")
        print(f"  win_rate: {trainer_feats.get('win_rate', 0):.3f}")
        print(f"  total_races: {trainer_feats.get('total_races', 0)}")


def test_training_data_builder():
    """Test TrainingDataBuilder"""
    print("\n" + "=" * 60)
    print("Testing TrainingDataBuilder")
    print("=" * 60)
    
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return
    
    builder = TrainingDataBuilder(db)
    
    # Check if we have races
    race_count = builder.db.db["races"].count_documents({})
    print(f"Total races in DB: {race_count}")
    
    if race_count == 0:
        print("❌ No races found - need to scrape data first")
        return
    
    # Try to build a small dataset (last month)
    from datetime import datetime, timedelta
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    print(f"\nBuilding dataset: {start_str} to {end_str}")
    
    try:
        df = builder.build_place_dataset(start_str, end_str, min_season_stats=1)
        
        if len(df) > 0:
            print(f"\n✅ Built dataset with {len(df)} samples")
            print(f"   Columns: {len(df.columns)}")
            print(f"   Place rate: {df['place'].mean():.3f}")
            
            # Show sample
            print("\n📋 Sample:")
            print(df[["horse_name", "jockey_name", "win_rate", "draw", "place"]].head(5))
        else:
            print("⚠️ No samples - need more data or adjust filters")
            
    except Exception as e:
        print(f"❌ Error building dataset: {e}")
        import traceback
        traceback.print_exc()


def test_race_features():
    """Test building features for a specific race"""
    print("\n" + "=" * 60)
    print("Testing Race Feature Building")
    print("=" * 60)
    
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return
    
    engineer = FeatureEngineer(db)
    
    # Get a recent race
    race = db.db["races"].find_one({
        "runners": {"$exists": True, "$ne": []}
    })
    
    if not race:
        print("❌ No races found")
        return
    
    race_id = race.get("race_id")
    print(f"Testing with race: {race_id}")
    
    features = engineer.build_race_features(race_id)
    
    if features:
        print(f"\n✅ Race has {len(features.get('horses', []))} horses")
        
        # Show top horses by rating
        horses = features.get("horses", [])
        if horses:
            sorted_horses = sorted(
                horses, 
                key=lambda x: x.get("current_rating", 0), 
                reverse=True
            )
            
            print("\n🏇 Top horses by rating:")
            for h in sorted_horses[:5]:
                print(f"  {h.get('horse_name')}: rating={h.get('current_rating')}, "
                      f"jockey={h.get('jockey_name')}")
    else:
        print("❌ Could not build features for race")


if __name__ == "__main__":
    print("🧪 ML Feature Engineering Test\n")
    
    test_feature_engineer()
    test_race_features()
    test_training_data_builder()
    
    print("\n" + "=" * 60)
    print("✅ Tests complete")
    print("=" * 60)
