"""
Feature Engineer for HKJC Racing ML Models
Extracts ML-ready features from MongoDB data
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from src.database.connection import DatabaseConnection as Database
from src.utils import logger


class FeatureEngineer:
    """
    Main feature engineering class
    
    Extracts features for:
    - Horse factors (performance, distance, class)
    - Jockey factors (win rate, recent form)
    - Trainer factors (win rate, season stats)
    - Race factors (distance, class, track)
    - Matchup factors (horse vs jockey/trainer combo)
    """
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.cache = {}  # Cache for repeated queries
    
    def get_horse_features(self, horse_id: str, race_date: str, race_info: Dict) -> Dict:
        """
        Extract all horse-related features for a race
        
        Args:
            horse_id: HKJC horse ID
            race_date: Race date (YYYY-MM-DD)
            race_info: Race metadata (distance, venue, class, etc.)
            
        Returns:
            Dict of horse features
        """
        horse = self.db.db["horses"].find_one({"hkjc_horse_id": horse_id})
        
        if not horse:
            logger.warning(f"Horse not found: {horse_id}")
            return self._empty_horse_features()
        
        # Get distance stats from separate collection
        distance_stats = self.db.db["horse_distance_stats"].find_one({"hkjc_horse_id": horse_id})
        
        features = {
            # Basic info
            "horse_id": horse_id,
            "horse_name": horse.get("name", ""),
            "age": horse.get("age", 0),
            "sex": horse.get("sex", ""),
            "country": horse.get("country", ""),
            "import_type": horse.get("import_type", ""),
            
            # Rating features
            "current_rating": horse.get("current_rating", 0) or 0,
            "initial_rating": horse.get("initial_rating", 0) or 0,
            "season_start_rating": horse.get("season_start_rating", 0) or 0,
            "rating_change": (horse.get("current_rating", 0) or 0) - (horse.get("season_start_rating", 0) or 0),
            
            # Career stats (from horses collection)
            "career_starts": horse.get("career_starts", 0) or 0,
            "career_wins": horse.get("career_wins", 0) or 0,
            "career_seconds": horse.get("career_seconds", 0) or 0,
            "career_thirds": horse.get("career_thirds", 0) or 0,
            "career_win_rate": 0,
            "career_place_rate": 0,
            
            # Season prize money
            "season_prize": horse.get("season_prize", 0) or 0,
            "total_prize": horse.get("total_prize", 0) or 0,
            
            # Trainer
            "trainer": horse.get("trainer", ""),
            
            # Distance performance (from horse_distance_stats)
            "distance_stats": self._get_distance_features(
                distance_stats.get("distance_performance", []) if distance_stats else [],
                race_info.get("distance", 0),
                race_info.get("venue", "")
            ),
            
            # Track performance
            "track_stats": self._get_track_performance(
                distance_stats.get("track_performance", []) if distance_stats else [],
                race_info.get("venue", "")
            ),
            
            # Recent form (from horse_race_history)
            "recent_form": self._get_recent_form(horse_id, race_date, num_races=10),
            
            # Days since last race
            "days_since_last": self._get_days_since_last_race(horse_id, race_date),
            "days_rest": self._get_days_since_last_race(horse_id, race_date),
            
            # Sire/dam info
            "sire": horse.get("sire", ""),
            "dam": horse.get("dam", ""),
        }
        
        # Calculate derived rates
        if features["career_starts"] > 0:
            features["career_win_rate"] = features["career_wins"] / features["career_starts"]
            features["career_place_rate"] = (
                features["career_wins"] + 
                features["career_seconds"] + 
                features["career_thirds"]
            ) / features["career_starts"]
        
        return features
    
    def get_jockey_features(self, jockey_name: str, season: Optional[str] = None) -> Dict:
        """
        Extract jockey features
        
        Args:
            jockey_name: Jockey name
            season: Season year (e.g., "2025-2026")
            
        Returns:
            Dict of jockey features
        """
        if not jockey_name:
            return self._empty_jockey_features()
        
        season = season or self._get_current_season()
        
        # Try to find jockey by name
        jockey = self.db.db["jockeys"].find_one({"name": jockey_name})
        
        if not jockey:
            # Try alternate search
            jockey = self.db.db["jockeys"].find_one({
                "name": {"$regex": jockey_name, "$options": "i"}
            })
        
        if not jockey:
            logger.warning(f"Jockey not found: {jockey_name}")
            return self._empty_jockey_features()
        
        wins = jockey.get("wins", 0) or 0
        total = jockey.get("total_rides", 0) or 0
        
        features = {
            "jockey_name": jockey_name,
            "wins": wins,
            "seconds": jockey.get("seconds", 0) or 0,
            "thirds": jockey.get("thirds", 0) or 0,
            "total_rides": total,
            "win_rate": wins / total if total > 0 else 0,
            "place_rate": (wins + jockey.get("seconds", 0) + jockey.get("thirds", 0)) / total if total > 0 else 0,
            "prize_money": jockey.get("prize_money_int", 0) or 0,
            "season": season,
        }
        
        return features
    
    def get_trainer_features(self, trainer_name: str, season: Optional[str] = None) -> Dict:
        """
        Extract trainer features
        
        Args:
            trainer_name: Trainer name
            season: Season year
            
        Returns:
            Dict of trainer features
        """
        if not trainer_name:
            return self._empty_trainer_features()
        
        season = season or self._get_current_season()
        
        # Try to find trainer by name
        trainer = self.db.db["trainers"].find_one({"name": trainer_name})
        
        if not trainer:
            # Try alternate search
            trainer = self.db.db["trainers"].find_one({
                "name": {"$regex": trainer_name, "$options": "i"}
            })
        
        if not trainer:
            logger.warning(f"Trainer not found: {trainer_name}")
            return self._empty_trainer_features()
        
        wins = trainer.get("wins", 0) or 0
        total = trainer.get("total_races", 0) or 0
        
        features = {
            "trainer_name": trainer_name,
            "wins": wins,
            "seconds": trainer.get("seconds", 0) or 0,
            "thirds": trainer.get("thirds", 0) or 0,
            "total_races": total,
            "win_rate": wins / total if total > 0 else 0,
            "place_rate": (wins + trainer.get("seconds", 0) + trainer.get("thirds", 0)) / total if total > 0 else 0,
            "prize_money": trainer.get("prize_money_int", 0) or 0,
            "total_horses": trainer.get("total_horses", 0) or 0,
            "season": season,
        }
        
        return features
    
    def get_race_features(self, race_info: Dict, all_horses: List[Dict]) -> Dict:
        """
        Extract race-level features
        
        Args:
            race_info: Race metadata
            all_horses: List of horse IDs in this race
            
        Returns:
            Dict of race features
        """
        # Get average rating of horses in race
        ratings = []
        for h in all_horses:
            horse_id = h.get("horse_id") if isinstance(h, dict) else h
            if isinstance(horse_id, dict):
                horse_id = horse_id.get("horse_id")
            horse = self.db.db["horses"].find_one({"hkjc_horse_id": horse_id})
            if horse and horse.get("current_rating"):
                ratings.append(horse.get("current_rating"))
        
        features = {
            "race_date": race_info.get("date", ""),
            "venue": race_info.get("venue", ""),
            "race_no": race_info.get("race_no", 0),
            "distance": race_info.get("distance", 0),
            "course": race_info.get("course", "TURF"),
            "track_condition": race_info.get("track_condition", ""),
            "race_class": race_info.get("race_class", ""),
            "prize": race_info.get("prize", 0),
            "total_runners": len(all_horses),
            
            # Horse composition
            "avg_horse_rating": sum(ratings) / len(ratings) if ratings else 0,
            "max_horse_rating": max(ratings) if ratings else 0,
            "min_horse_rating": min(ratings) if ratings else 0,
            
            # Class indicators
            "is_class_1": 1 if "1" in str(race_info.get("race_class", "")) else 0,
            "is_class_2": 1 if "2" in str(race_info.get("race_class", "")) else 0,
            "is_class_3": 1 if "3" in str(race_info.get("race_class", "")) else 0,
            "is_class_4": 1 if "4" in str(race_info.get("race_class", "")) else 0,
        }
        
        return features
    
    def get_matchup_features(
        self, 
        horse_id: str, 
        jockey_name: str, 
        trainer_name: str,
        season: Optional[str] = None
    ) -> Dict:
        """
        Extract matchup features (horse-jockey-trainer combos)
        
        Args:
            horse_id: Horse ID
            jockey_name: Jockey name
            trainer_name: Trainer name
            season: Season year
            
        Returns:
            Dict of matchup features
        """
        if not horse_id:
            return self._empty_matchup_features()
        
        # Horse-jockey combo
        hj_history = list(self.db.db["horse_race_history"].find({
            "hkjc_horse_id": horse_id,
            "jockey": {"$regex": jockey_name, "$options": "i"} if jockey_name else None
        }).sort("date", -1).limit(20))
        
        hj_history = [h for h in hj_history if h.get("jockey")]  # Filter None
        
        hj_wins = sum(1 for h in hj_history if self._parse_position(h.get("position")) == 1)
        hj_places = sum(1 for h in hj_history if self._parse_position(h.get("position", 0)) <= 3)
        
        # Horse-trainer combo
        ht_history = list(self.db.db["horse_race_history"].find({
            "hkjc_horse_id": horse_id,
            "trainer": {"$regex": trainer_name, "$options": "i"} if trainer_name else None
        }).sort("date", -1).limit(20))
        
        ht_history = [h for h in ht_history if h.get("trainer")]
        
        ht_wins = sum(1 for h in ht_history if self._parse_position(h.get("position")) == 1)
        ht_places = sum(1 for h in ht_history if self._parse_position(h.get("position", 0)) <= 3)
        
        features = {
            "horse_jockey_races": len(hj_history),
            "horse_jockey_wins": hj_wins,
            "horse_jockey_places": hj_places,
            "horse_jockey_win_rate": hj_wins / len(hj_history) if hj_history else 0,
            "horse_jockey_place_rate": hj_places / len(hj_history) if hj_history else 0,
            
            "horse_trainer_races": len(ht_history),
            "horse_trainer_wins": ht_wins,
            "horse_trainer_places": ht_places,
            "horse_trainer_win_rate": ht_wins / len(ht_history) if ht_history else 0,
            "horse_trainer_place_rate": ht_places / len(ht_history) if ht_history else 0,
        }
        
        return features
    
    def build_race_features(self, race_id: str) -> Dict:
        """
        Build complete feature set for a race
        
        Args:
            race_id: Race ID
            
        Returns:
            Complete feature dict with all horses
        """
        # Get race info from races collection
        race = self.db.db["races"].find_one({"race_id": race_id})
        
        if not race:
            # Try alternate ID formats
            race = self.db.db["races"].find_one({"hkjc_race_id": race_id})
        
        if not race:
            logger.error(f"Race not found: {race_id}")
            return {}
        
        # Parse race info
        race_info = {
            "date": race.get("race_date", ""),
            "venue": race.get("venue", ""),
            "race_no": race.get("race_no", 0),
            "distance": race.get("distance", 0),
            "course": race.get("course", "TURF"),
            "track_condition": race.get("track_condition", ""),
            "race_class": race.get("class", ""),
            "prize": race.get("prize", 0),
        }
        
        # Get runners from results
        results = race.get("results", [])
        if not results:
            logger.warning(f"No results in race: {race_id}")
            return {}
        
        # Build features for each horse
        horse_features_list = []
        
        for runner in results:
            # Try to find horse ID by name
            horse_name = runner.get("horse_name", "")
            horse_id = self._find_horse_id_by_name(horse_name)
            
            jockey = runner.get("jockey", "")
            trainer = runner.get("trainer", "")
            draw = runner.get("draw", 0)
            
            # Get base features
            horse_feats = self.get_horse_features(horse_id or "", race_info["date"], race_info)
            horse_feats["horse_name"] = horse_name
            
            jockey_feats = self.get_jockey_features(jockey)
            trainer_feats = self.get_trainer_features(trainer)
            
            matchup_feats = self.get_matchup_features(
                horse_id or "", jockey, trainer
            )
            
            # Combine all features
            combined = {
                **horse_feats,
                **jockey_feats,
                **trainer_feats,
                **matchup_feats,
                "draw": draw,
                "draw_advantage": self.get_draw_advantage(
                    draw, race_info.get("venue", ""), race_info.get("distance", 0)
                ),
                "horse_number": runner.get("horse_number", 0),
                "win_odds": runner.get("win_odds", 0) or 0,
            }
            
            # Add actual result (if available)
            position = self._parse_position(runner.get("rank") or runner.get("position"))
            if position > 0:
                combined["actual_rank"] = position
            
            horse_features_list.append(combined)
        
        # Add race-level features
        race_feats = self.get_race_features(race_info, horse_features_list)
        
        return {
            "race_id": race_id,
            "race_info": race_feats,
            "horses": horse_features_list,
        }
    
    def get_draw_advantage(self, draw: int, venue: str, distance: int) -> float:
        """
        Calculate draw advantage/disadvantage.
        
        Rules:
        - ST 1000m: outer draw (high draw) = advantage
        - HV all distances: inner draw (low draw) = advantage
        
        Returns:
            Positive = advantage, Negative = disadvantage, 0 = neutral
        """
        if draw is None or draw == 0:
            return 0
        
        if venue == "HV":
            # Happy Valley: inner draw is always better
            # draw 1=最內檔(advantage) to draw 14=最外檔
            return 8 - draw  # draw 1 → +7, draw 8 → 0, draw 14 → -6
        
        if venue == "ST" and distance == 1000:
            # Sha Tin 1000m: outer draw is better (can get out from inside)
            return draw - 8  # draw 14 → +6, draw 8 → 0, draw 1 → -7
        
        # ST other distances: no strong draw bias
        return 0
    
    def _find_horse_id_by_name(self, horse_name: str) -> Optional[str]:
        """Find horse ID by name"""
        if not horse_name:
            return None
        
        horse = self.db.db["horses"].find_one({"name": horse_name})
        if horse:
            return horse.get("hkjc_horse_id")
        
        # Try partial match
        horse = self.db.db["horses"].find_one({
            "name": {"$regex": horse_name, "$options": "i"}
        })
        
        if horse:
            return horse.get("hkjc_horse_id")
        
        return None
    
    def _parse_position(self, pos) -> int:
        """Parse position to integer"""
        if pos is None:
            return 0
        
        try:
            return int(pos)
        except (ValueError, TypeError):
            # Handle "01" format
            try:
                return int(str(pos).strip())
            except Exception:
                return 0
    
    def _get_distance_features(self, distance_stats: List, race_distance: int, venue: str) -> Dict:
        """Extract distance-specific performance features"""
        if not distance_stats:
            return {
                "distance_wins": 0,
                "distance_runs": 0,
                "distance_win_rate": 0,
                "distance_place_rate": 0,
            }
        
        # Find matching distance
        race_dist_str = f"{race_distance}米"
        
        for ds in distance_stats:
            ds_dist = ds.get("distance", "")
            
            # Simple matching
            if race_dist_str in ds_dist or ds_dist in race_dist_str:
                runs = ds.get("total_runs", 0) or 0
                wins = ds.get("first", 0) or 0
                seconds = ds.get("second", 0) or 0
                thirds = ds.get("third", 0) or 0
                places = wins + seconds + thirds
                
                return {
                    "distance_wins": wins,
                    "distance_runs": runs,
                    "distance_win_rate": wins / runs if runs > 0 else 0,
                    "distance_place_rate": places / runs if runs > 0 else 0,
                }
        
        # No matching distance found
        return {
            "distance_wins": 0,
            "distance_runs": 0,
            "distance_win_rate": 0,
            "distance_place_rate": 0,
        }
    
    def _get_track_performance(self, track_stats: List, venue: str) -> Dict:
        """Extract track-specific performance"""
        if not track_stats:
            return {
                "track_wins": 0,
                "track_runs": 0,
                "track_win_rate": 0,
            }
        
        # Find matching venue
        venue_map = {
            "沙田": "草地",
            "ST": "草地",
            "跑馬地": "草地",
            "HV": "草地",
        }
        
        for ts in track_stats:
            surface = ts.get("surface", "")
            
            if "草" in venue or "TURF" in str(venue).upper():
                if "草地" in surface or "Turf" in surface:
                    runs = ts.get("starts", 0) or 0
                    wins = ts.get("win", 0) or 0
                    return {
                        "track_wins": wins,
                        "track_runs": runs,
                        "track_win_rate": wins / runs if runs > 0 else 0,
                    }
        
        return {
            "track_wins": 0,
            "track_runs": 0,
            "track_win_rate": 0,
        }
    
    def _get_recent_form(self, horse_id: str, race_date: str, num_races: int = 10) -> Dict:
        """Get recent race form"""
        if not horse_id:
            return self._empty_recent_form()
        
        # Convert date format if needed
        try:
            # race_date might be YYYY-MM-DD or YYYY/MM/DD
            race_dt = datetime.strptime(race_date.replace("/", "-"), "%Y-%m-%d")
        except Exception:
            race_dt = datetime.now()
        
        history = list(self.db.db["horse_race_history"].find({
            "hkjc_horse_id": horse_id,
        }).sort("date", -1).limit(num_races))
        
        if not history:
            return self._empty_recent_form()
        
        ranks = []
        for h in history:
            pos = self._parse_position(h.get("position"))
            if pos > 0:
                ranks.append(pos)
        
        if not ranks:
            return self._empty_recent_form()
        
        wins = sum(1 for r in ranks if r == 1)
        places = sum(1 for r in ranks if r <= 3)
        
        return {
            "recent_races": len(ranks),
            "recent_wins": wins,
            "recent_places": places,
            "recent_avg_rank": sum(ranks) / len(ranks) if ranks else 0,
            "recent_win_rate": wins / len(ranks) if history else 0,
        }
    
    def _get_days_since_last_race(self, horse_id: str, race_date: str) -> int:
        """Get days since last race"""
        if not horse_id:
            return 999
        
        try:
            race_dt = datetime.strptime(race_date.replace("/", "-"), "%Y-%m-%d")
        except Exception:
            return 999
        
        last_race = self.db.db["horse_race_history"].find_one(
            {"hkjc_horse_id": horse_id},
            sort=[("date", -1)]
        )
        
        if not last_race:
            return 999  # No previous races
        
        try:
            last_date = last_race.get("date", "")
            # Handle date formats like "08/03/26"
            last_dt = datetime.strptime(last_date.replace("/", "-"), "%d/%m/%y")
            return (race_dt - last_dt).days
        except Exception:
            return 999
    
    def _get_current_season(self) -> str:
        """Get current season string"""
        now = datetime.now()
        if now.month >= 7:
            return f"{now.year}-{now.year + 1}"
        return f"{now.year - 1}-{now.year}"
    
    def _empty_horse_features(self) -> Dict:
        """Return empty horse features"""
        return {
            "horse_id": "",
            "horse_name": "",
            "age": 0,
            "sex": "",
            "country": "",
            "current_rating": 0,
            "rating_change": 0,
            "career_starts": 0,
            "career_wins": 0,
            "career_seconds": 0,
            "career_thirds": 0,
            "career_win_rate": 0,
            "career_place_rate": 0,
            "season_prize": 0,
            "distance_wins": 0,
            "distance_runs": 0,
            "distance_win_rate": 0,
            "recent_races": 0,
            "recent_wins": 0,
            "recent_avg_rank": 0,
            "days_since_last": 999,
        }
    
    def _empty_jockey_features(self) -> Dict:
        """Return empty jockey features"""
        return {
            "jockey_name": "",
            "wins": 0,
            "total_rides": 0,
            "win_rate": 0,
            "place_rate": 0,
        }
    
    def _empty_trainer_features(self) -> Dict:
        """Return empty trainer features"""
        return {
            "trainer_name": "",
            "wins": 0,
            "total_races": 0,
            "win_rate": 0,
            "place_rate": 0,
        }
    
    def _empty_matchup_features(self) -> Dict:
        """Return empty matchup features"""
        return {
            "horse_jockey_races": 0,
            "horse_jockey_wins": 0,
            "horse_jockey_win_rate": 0,
            "horse_trainer_races": 0,
            "horse_trainer_wins": 0,
            "horse_trainer_win_rate": 0,
        }
    
    def _empty_recent_form(self) -> Dict:
        """Return empty recent form"""
        return {
            "recent_races": 0,
            "recent_wins": 0,
            "recent_places": 0,
            "recent_avg_rank": 0,
            "recent_win_rate": 0,
        }


if __name__ == "__main__":
    # Test
    db = Database()
    db.connect()
    engineer = FeatureEngineer(db)
    print("Feature Engineer initialized")
    
    # Example: Get features for a specific horse
    # features = engineer.get_horse_features("HK_2024_L001", "2026-03-15", {"distance": 1200})
    # print(features)
