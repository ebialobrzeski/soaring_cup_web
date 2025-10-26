"""Configuration constants for Soaring CUP Editor."""

# Style options mapping
STYLE_OPTIONS = {
    0: "Unknown",
    1: "Waypoint",
    2: "Airfield (grass)",
    3: "Outlanding",
    4: "Gliding airfield",
    5: "Airfield (solid)",
    6: "Mountain Pass",
    7: "Mountain Top",
    8: "Transmitter Mast",
    9: "VOR",
    10: "NDB",
    11: "Cooling Tower",
    12: "Dam",
    13: "Tunnel",
    14: "Bridge",
    15: "Power Plant",
    16: "Castle",
    17: "Intersection",
    18: "Marker",
    19: "Reporting Point",
    20: "PG Take Off",
    21: "PG Landing"
}

# Reverse mapping for style labels
STYLE_LABELS = {v: k for k, v in STYLE_OPTIONS.items()}

# API Configuration
ELEVATION_API_URL = "https://api.open-elevation.com/api/v1/lookup"
ELEVATION_API_TIMEOUT = 5

# Coordinate validation ranges
LATITUDE_MIN = -90
LATITUDE_MAX = 90
LONGITUDE_MIN = -180
LONGITUDE_MAX = 180
