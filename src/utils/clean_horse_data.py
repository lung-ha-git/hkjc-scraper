"""
Horse Data Cleaner and Schema Updater
Clean existing horse data and update schema
"""

import re
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.database.connection import DatabaseConnection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clean_horse_data():
    """Clean and standardize existing horse data"""
    print("🧹 Cleaning Horse Data")
    print("=" * 60)
    
    db = DatabaseConnection()
    if not db.connect():
        print("❌ Cannot connect to MongoDB")
        return
    
    # Get all horses
    horses = list(db.horses.find({}))
    print(f"📊 Found {len(horses)} horses to clean")
    
    cleaned_count = 0
    error_count = 0
    
    for horse in horses:
        try:
            original_name = horse.get('name', '')
            
            # Extract rating from name (e.g., "祝願\n\t(118)")
            rating_match = re.search(r'\((\d+)\)', original_name)
            rating = int(rating_match.group(1)) if rating_match else None
            
            # Clean name - remove everything after newline and trim
            clean_name = original_name.split('\n')[0].strip()
            clean_name = re.sub(r'\s+', ' ', clean_name)  # Normalize spaces
            
            # Skip unnamed horses or invalid entries
            if not clean_name or clean_name in ['未命名馬匹', '']:
                db.horses.delete_one({"_id": horse["_id"]})
                continue
            
            # Create standardized horse_id
            horse_id = f"HK_{clean_name}"
            
            # Build updated document
            updated_horse = {
                "horse_id": horse_id,
                "name_zh": clean_name,
                "name_en": None,  # To be filled later
                "rating": rating,
                "rating_history": [],  # For tracking rating changes
                "age": None,  # To be scraped
                "sex": None,  # G/H/C/F - Gelding/Horse/Colt/Filly
                "color": None,  # 毛色
                "country": None,  # 出生地
                "trainer": None,  # 練馬師
                "owner": None,  # 馬主
                "breeder": None,  # 繁殖者
                "arrival_date": None,  # 來港日期
                "total_starts": 0,
                "total_wins": 0,
                "total_places": 0,
                "career_earnings": 0,
                "type": horse.get('type', '未知'),  # 二字馬/三字馬/四字馬
                "active": True,
                "scraped_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "raw_data": {
                    "original_name": original_name,
                    "source": horse.get('source', 'unknown')
                }
            }
            
            # Update in database
            db.horses.replace_one(
                {"_id": horse["_id"]},
                updated_horse
            )
            cleaned_count += 1
            
        except Exception as e:
            logger.error(f"Error cleaning horse {horse.get('name')}: {e}")
            error_count += 1
    
    # Show stats
    total_after = db.horses.count_documents({})
    
    print(f"\n✅ Cleaning complete!")
    print(f"   Cleaned: {cleaned_count}")
    print(f"   Errors: {error_count}")
    print(f"   Total in DB: {total_after}")
    
    # Show sample
    print("\n📋 Sample cleaned horse:")
    sample = db.horses.find_one()
    if sample:
        print(f"   ID: {sample.get('horse_id')}")
        print(f"   Name: {sample.get('name_zh')}")
        print(f"   Rating: {sample.get('rating')}")
        print(f"   Type: {sample.get('type')}")
    
    db.disconnect()


if __name__ == "__main__":
    clean_horse_data()
