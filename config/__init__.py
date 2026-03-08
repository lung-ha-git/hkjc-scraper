"""
Configuration for HKJC Racing Project
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

# MongoDB configuration
MONGODB = {
    "host": os.getenv("MONGODB_HOST", "localhost"),
    "port": int(os.getenv("MONGODB_PORT", 27017)),
    "database": os.getenv("MONGODB_DATABASE", "hkjc_racing"),
    "connection_string": os.getenv("MONGODB_URI", "")
}

# Scraper configuration
SCRAPER = {
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "timeout": 30,
    "retry_count": 3,
    "delay_between_requests": 2,  # seconds
}

# HKJC URLs
HKJC = {
    "base_url": "https://racing.hkjc.com",
    "results_url": "/racing/information/English/Racing/LocalResults.aspx",
    "race_card_url": "/racing/information/English/Racing/RaceCard.aspx",
}

# API configuration
API = {
    "host": "0.0.0.0",
    "port": 8000,
    "debug": os.getenv("DEBUG", "true").lower() == "true"
}

# ML configuration (for future phases)
ML = {
    "model_path": PROJECT_ROOT / "models",
    "features": [
        "horse_age", "horse_rating", "jockey_win_rate", 
        "trainer_win_rate", "distance", "draw", "weight"
    ]
}
