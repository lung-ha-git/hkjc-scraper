"""
HKJC Project Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
RAW_DATA_DIR.mkdir(exist_ok=True)
PROCESSED_DATA_DIR.mkdir(exist_ok=True)

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "hkjc_racing")

# HKJC URLs
HKJC_BASE_URL = "https://racing.hkjc.com"
HKJC_RESULTS_URL = "/racing/information/English/Racing/LocalResults.aspx"

# Scraper Configuration
SCRAPER_DELAY_MIN = 3  # Minimum delay between requests (seconds)
SCRAPER_DELAY_MAX = 6  # Maximum delay between requests (seconds)
SCRAPER_MAX_RETRIES = 3
SCRAPER_TIMEOUT = 30

# Data Fetch Configuration
FETCH_DAYS_HISTORY = 30  # Number of days to fetch initially
FETCH_DAYS_RECENT = 7    # Number of days for recent updates

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

# API Configuration (for future FastAPI)
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_DEBUG = os.getenv("API_DEBUG", "false").lower() == "true"
