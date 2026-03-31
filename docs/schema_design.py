"""
HKJC Extended Schema Design
Collections structure for comprehensive horse data
"""

# ============================================
# Collection 1: horses (existing - enhanced)
# ============================================
HORSE_SCHEMA = {
    "_id": ObjectId,
    
    # IDs
    "horse_id": "HK_祝願",           # 内部ID
    "hkjc_horse_id": "S927",          # HKJC官方ID ⭐
    
    # Basic Info
    "name_zh": "祝願",
    "name_en": "Wishful",
    "country": "澳洲",
    "age": 4,
    "sex": "G",                       # G=閹, H=公, F=母, C=雄
    "color": "棗",
    
    # Import Info
    "import_type": "自購馬",
    "import_date": "16/09/2024",
    "arrival_date": "23/02/2026",
    
    # People
    "trainer": "姚本輝",
    "trainer_id": "trainer_姚本輝",
    "owner": "君匯團體",
    "breeder": None,
    
    # Pedigree
    "pedigree": {
        "sire": "Alabama Express",      # 父系
        "dam": "World Awaits",          # 母系
        "damsire": "Written Tycoon"     # 外祖父
    },
    
    # Current Status
    "current_location": "香港",
    "active": True,
    "current_rating": 61,
    "initial_rating": 65,
    
    # Career Stats (cumulative)
    "career_stats": {
        "total_starts": 8,
        "wins": 0,
        "seconds": 0,
        "thirds": 2,
        "total_prize_money": 604500,
        "season_prize_money": 604500
    },
    
    # Recent Activity
    "recent_10_runs": 0,              # 最近10個賽馬日出賽場數
    
    # Metadata
    "scraped_at": "2026-03-08",
    "last_updated": "2026-03-08"
}

# ============================================
# Collection 2: horse_race_history (NEW)
# 往績紀錄 - 每場比賽獨立文檔
# ============================================
RACE_HISTORY_SCHEMA = {
    "_id": ObjectId,
    
    # IDs
    "history_id": "HR_S927_20250301",  # 組合ID
    "hkjc_horse_id": "S927",
    "horse_id": "HK_祝願",
    
    # Race Info
    "race_date": "2025-03-01",
    "racecourse": "ST",               # ST/HV
    "race_no": 5,
    "distance": 1400,                 # 米
    "track_condition": "GF",
    "race_class": "Class 4",
    
    # Performance
    "finish_position": 3,             # 名次
    "finish_time": "1:22.45",         # 完成時間
    "margin": "1-3/4",                # 距離
    "draw": 8,                        # 檔位
    "weight": 133,                    # 負磅 (磅)
    "rating": 65,                     # 當時評分
    
    # People
    "jockey": "潘頓",
    "jockey_id": "jockey_潘頓",
    "trainer": "姚本輝",
    
    # Odds
    "odds": 8.5,                      # 獨贏賠率
    
    # Sectional Times (如果有的話)
    "sectional_times": {
        "400m": "23.45",
        "800m": "46.78",
        "1200m": "1:10.50"
    },
    
    # Metadata
    "scraped_at": "2026-03-08"
}

# ============================================
# Collection 3: horse_workouts (NEW)
# 晨操紀錄
# ============================================
WORKOUT_SCHEMA = {
    "_id": ObjectId,
    
    "hkjc_horse_id": "S927",
    "horse_id": "HK_祝願",
    
    # Workout Date
    "workout_date": "2025-03-05",
    "workout_time": "06:30",          # 操練時間
    
    # Location
    "venue": "沙田",                  # 沙田/從化/其他
    "track_surface": "全天候跑道",     # 草地/泥地/全天候
    
    # Details
    "distance": 1000,                 # 米
    "time": "1:01.5",                 # 時間
    "rider": "鄭進偉",                # 騎操者
    "rider_type": "騎師",             # 騎師/見習騎師/馬伕
    
    # Comments
    "comments": "走勢良俗",            # 狀態描述
    
    "scraped_at": "2026-03-08"
}

# ============================================
# Collection 4: horse_medical (NEW)
# 傷患紀錄 + 搬遷紀錄
# ============================================
MEDICAL_SCHEMA = {
    "_id": ObjectId,
    
    "hkjc_horse_id": "S927",
    "horse_id": "HK_祝願",
    
    # Event Info
    "event_date": "2025-02-15",
    "event_type": "injury",           # injury/movement/treatment
    
    # For Injuries
    "injury_type": "右前足不良於行",
    "severity": "輕微",                # 輕微/嚴重
    "treatment": "休息及治療",
    "recovery_time_days": 14,
    "vet_notes": "...",
    
    # For Movements
    "from_location": "沙田",
    "to_location": "從化",
    "movement_reason": "休養",
    
    # Status
    "resolved": True,
    "resolution_date": "2025-03-01",
    
    "scraped_at": "2026-03-08"
}

# ============================================
# Collection 5: horse_jerseys (NEW)
# 馬匹彩衣
# ============================================
JERSEY_SCHEMA = {
    "_id": ObjectId,
    
    "hkjc_horse_id": "S927",
    "horse_id": "HK_祝願",
    
    # Jersey Info
    "jersey_id": "J_S927",
    "colors": "紅白藍三色",             # 文字描述
    "color_codes": ["#FF0000", "#FFFFFF", "#0000FF"],
    
    # Image URLs (if available)
    "image_url": "https://racing.hkjc.com/.../S927_jersey.png",
    "image_data": None,                # Base64 encoded (optional)
    
    # Description
    "pattern": "紅袖白身藍帶",
    "design_notes": None,
    
    "scraped_at": "2026-03-08"
}

# ============================================
# Collection 6: horse_overseas_records (NEW)
# 海外賽績紀錄
# ============================================
OVERSEAS_SCHEMA = {
    "_id": ObjectId,
    
    "hkjc_horse_id": "S927",
    "horse_id": "HK_祝願",
    
    # Race Info
    "race_date": "2023-11-15",
    "country": "澳洲",
    "racecourse": "Flemington",
    
    # Performance
    "finish_position": 5,
    "distance": 1200,
    "prize_money_aud": 5000,
    "class": "Maiden",
    
    "scraped_at": "2026-03-08"
}
