"""Geo utilities and flight estimation helpers.

Provides:
  - Haversine distance, bearing, destination point
  - Geocoding via Nominatim
  - Flight time estimation (simplified MacCready)

Formerly the full route optimizer; route design is now handled by the AI model.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import requests as _requests

logger = logging.getLogger(__name__)

# Nominatim for forward-geocoding place names
_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlon = math.radians(lon2 - lon1)
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _destination(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    R = 6371.0
    d = dist_km / R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return round(math.degrees(lat2), 4), round(math.degrees(lon2), 4)


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode_place(
    name: str,
    bias_lat: float,
    bias_lon: float,
    radius_km: float = 300,
) -> Optional[tuple[float, float]]:
    """Resolve a place name to (lat, lon) using Nominatim, biased near a point."""
    try:
        resp = _requests.get(
            _NOMINATIM_SEARCH_URL,
            params={
                "q": name,
                "format": "json",
                "limit": 5,
                "viewbox": _viewbox(bias_lat, bias_lon, radius_km),
                "bounded": 1,
            },
            headers={"User-Agent": "GlidePlan/1.0"},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            logger.info("Nominatim: no results for '%s'", name)
            return None
        best = min(results, key=lambda r: _haversine(
            bias_lat, bias_lon, float(r["lat"]), float(r["lon"])))
        lat, lon = float(best["lat"]), float(best["lon"])
        logger.info("Geocoded '%s' → %.4f, %.4f (%s)", name, lat, lon, best.get("display_name", ""))
        return (lat, lon)
    except Exception:
        logger.warning("Nominatim geocode failed for '%s'", name, exc_info=True)
        return None


def _viewbox(lat: float, lon: float, radius_km: float) -> str:
    """Create a Nominatim viewbox string around a point."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"


# ---------------------------------------------------------------------------
# Flight time estimation
# ---------------------------------------------------------------------------

def estimate_flight_time(
    total_distance_km: float,
    glider_polar: Optional[dict] = None,
    avg_thermal_strength: Optional[float] = None,
    avg_wind_component: float = 0.0,
) -> dict:
    """Estimate flight duration and average speed.

    Uses simplified MacCready theory if glider polar is available.
    """
    if not glider_polar:
        avg_speed_kmh = 80.0
    else:
        v2 = glider_polar.get("v2_kmh", 120)
        w2 = abs(glider_polar.get("w2_ms", 1.0))
        mc = avg_thermal_strength or 1.5
        mc_speed = v2 * (1 + mc / (w2 * 3.6))
        avg_speed_kmh = min(mc_speed, 150)

    avg_speed_kmh += avg_wind_component * 1.852 * 0.3
    avg_speed_kmh = max(50, avg_speed_kmh)
    duration_hours = total_distance_km / avg_speed_kmh

    return {
        "estimated_duration_hours": round(duration_hours, 1),
        "estimated_speed_kmh": round(avg_speed_kmh, 0),
    }
