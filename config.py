"""Central settings. Values come from the .env file (see .env.example)."""
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pathsnap")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "English")

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "PathsnapPipeline/0.1 (student project, Bandung)"

# Hidden-gem proxy filter (same idea as the friend's pipeline)
MIN_RATING = 4.4
MIN_REVIEWS = 3
MAX_REVIEWS = 150
AI_MIN_CONFIDENCE = 0.6
PROMPT_VERSION = "v1"

# Dedup: two records of the same kind within this distance AND with similar names are duplicates
DEDUP_RADIUS_M = 50
DEDUP_NAME_SIMILARITY = 0.6

# Google match must be within this many meters of the OSM point
GOOGLE_MATCH_RADIUS_M = 150

# Price level thresholds (IDR). Our own assumption - adjust to taste.
# places: entrance fee per person / accommodations: price per night
PLACE_PRICE_LEVELS = [(0, "free"), (50_000, "budget"), (150_000, "moderate"), (500_000, "expensive")]
ACCOM_PRICE_LEVELS = [(300_000, "budget"), (800_000, "moderate"), (2_000_000, "expensive")]
