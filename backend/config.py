"""
Configuration settings for the soaring waypoint editor.
All environment variables are loaded here — never hardcode credentials elsewhere.
"""
import os
from dotenv import load_dotenv

# Load .env (single source of truth for all secrets and settings)
# override=True ensures .env values always win, even if env vars were
# inherited as empty strings from a parent/reloader process.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'), override=True)

# Flask
SECRET_KEY: str = os.environ.get('SECRET_KEY', 'CHANGE-ME-IN-PRODUCTION')
BASE_URL: str = os.environ.get('BASE_URL', '')

# Database
DATABASE_URL: str = os.environ.get('DATABASE_URL', '')

# AI Services (legacy direct fallback only — primary AI uses user-provided OpenRouter keys)
GEMINI_API_KEY: str = os.environ.get('GEMINI_API_KEY', '')
GROQ_API_KEY: str = os.environ.get('GROQ_API_KEY', '')
DEEPSEEK_API_KEY: str = os.environ.get('DEEPSEEK_API_KEY', '')

# Weather APIs
IMGW_API_BASE_URL: str = os.environ.get('IMGW_API_BASE_URL', 'https://danepubliczne.imgw.pl/api/data')
WINDY_API_KEY: str = os.environ.get('WINDY_API_KEY', '')
OPENWEATHER_API_KEY: str = os.environ.get('OPENWEATHER_API_KEY', '')
NOAA_API_KEY: str = os.environ.get('NOAA_API_KEY', '')

# Airspace APIs
OPENAIP_API_KEY: str = os.environ.get('OPENAIP_API_KEY', '')
ICAO_API_KEY: str = os.environ.get('ICAO_API_KEY', '')
# Email (Resend)
RESEND_API_KEY: str       = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_ADDRESS: str  = os.environ.get('RESEND_FROM_ADDRESS', 'noreply@glideplan.org')
# User tier limits — enforced server-side only
TIER_LIMITS: dict = {
    'free': {
        'max_waypoint_files': 5,
        'max_saved_tasks': 10,
        'can_set_private': False,
        'ai_planner': False,
    },
    'premium': {
        'max_waypoint_files': 50,
        'max_saved_tasks': 100,
        'can_set_private': True,
        'ai_planner': True,
    },
    'admin': {
        'max_waypoint_files': None,
        'max_saved_tasks': None,
        'can_set_private': True,
        'ai_planner': True,
    },
}

# XCSoar waypoint style options
STYLE_OPTIONS = [
    (1, "Normal waypoint"),
    (2, "Airfield (grass)"),
    (3, "Outlanding"),
    (4, "Gliding site"),
    (5, "Airfield (solid)"),
    (6, "Mountain pass"),
    (7, "Mountain top"),
    (8, "Transmitter mast"),
    (9, "VOR"),
    (10, "NDB"),
    (11, "Cooling tower"),
    (12, "Dam"),
    (13, "Tunnel"),
    (14, "Bridge"),
    (15, "Power plant"),
    (16, "Castle"),
    (17, "Intersection"),
    (18, "Marker"),
    (19, "Control tower"),
    (20, "Thermal"),
    (21, "Town"),
    (22, "Settlement")
]