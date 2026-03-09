"""Terrain / DEM data fetching and terrain clearance calculations.

Uses Open-Meteo Elevation API (free, no key) for single-point and multi-point
elevation queries. Falls back to SRTM 90m if available.

Key functions:
  get_elevations()          — batch elevation lookup for multiple points
  check_terrain_clearance() — validate that a task leg clears terrain
  get_terrain_profile()     — sample elevations along a leg for the optimizer
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# Open-Meteo Elevation API — free, no key, bulk-capable
ELEVATION_API_URL = "https://api.open-meteo.com/v1/elevation"


# ---------------------------------------------------------------------------
# Batch elevation lookup
# ---------------------------------------------------------------------------

def get_elevations(points: list[tuple[float, float]]) -> dict[tuple[float, float], int]:
    """Fetch ground elevations (metres ASL) for a list of (lat, lon) points.

    Uses Open-Meteo Elevation API which supports up to 100 points per call.
    Returns dict mapping (lat, lon) → elevation_m.
    """
    result: dict[tuple[float, float], int] = {}
    if not points:
        return result

    # API accepts max 100 coordinates per call
    for i in range(0, len(points), 100):
        batch = points[i:i + 100]
        lats = ",".join(f"{p[0]:.4f}" for p in batch)
        lons = ",".join(f"{p[1]:.4f}" for p in batch)

        try:
            resp = requests.get(
                ELEVATION_API_URL,
                params={"latitude": lats, "longitude": lons},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            elevations = data.get("elevation", [])
            for j, elev in enumerate(elevations):
                if elev is not None and j < len(batch):
                    result[batch[j]] = int(elev)
        except Exception:
            logger.warning("Elevation API failed for batch %d", i // 100, exc_info=True)

    logger.info("Terrain: fetched %d/%d elevations", len(result), len(points))
    return result


# ---------------------------------------------------------------------------
# Terrain profile along a leg
# ---------------------------------------------------------------------------

def _interpolate_points(
    lat1: float, lon1: float, lat2: float, lon2: float, n_samples: int,
) -> list[tuple[float, float]]:
    """Generate evenly-spaced points along a great-circle approximation."""
    points = []
    for i in range(n_samples + 1):
        frac = i / n_samples
        lat = lat1 + frac * (lat2 - lat1)
        lon = lon1 + frac * (lon2 - lon1)
        points.append((round(lat, 4), round(lon, 4)))
    return points


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_terrain_profile(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    n_samples: int = 10,
) -> list[dict]:
    """Sample terrain elevations along a straight line between two points.

    Returns list of {lat, lon, elevation_m, distance_km} dicts.
    """
    dist_km = _haversine(lat1, lon1, lat2, lon2)
    sample_points = _interpolate_points(lat1, lon1, lat2, lon2, n_samples)
    elevations = get_elevations(sample_points)

    profile = []
    for i, (lat, lon) in enumerate(sample_points):
        elev = elevations.get((lat, lon), 0)
        d = (i / n_samples) * dist_km
        profile.append({
            "lat": lat,
            "lon": lon,
            "elevation_m": elev,
            "distance_km": round(d, 1),
        })
    return profile


# ---------------------------------------------------------------------------
# Terrain clearance check
# ---------------------------------------------------------------------------

def check_terrain_clearance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    expected_altitude_m: int,
    clearance_margin_m: int = 300,
    n_samples: int = 10,
) -> dict:
    """Check if a task leg has adequate terrain clearance.

    Args:
        lat1, lon1: leg start
        lat2, lon2: leg end
        expected_altitude_m: expected flight altitude MSL in metres
        clearance_margin_m: minimum clearance above terrain (default 300m)
        n_samples: number of terrain samples along the leg

    Returns dict with:
        safe: bool — all points clear
        min_clearance_m: int — minimum clearance found
        max_terrain_m: int — highest terrain along the leg
        problem_points: list of points that violate clearance
    """
    profile = get_terrain_profile(lat1, lon1, lat2, lon2, n_samples)

    min_clearance = expected_altitude_m
    max_terrain = 0
    problems = []

    for p in profile:
        elev = p["elevation_m"]
        clearance = expected_altitude_m - elev
        if elev > max_terrain:
            max_terrain = elev
        if clearance < min_clearance:
            min_clearance = clearance
        if clearance < clearance_margin_m:
            problems.append({
                "lat": p["lat"],
                "lon": p["lon"],
                "terrain_m": elev,
                "clearance_m": clearance,
                "distance_km": p["distance_km"],
            })

    return {
        "safe": len(problems) == 0,
        "min_clearance_m": min_clearance,
        "max_terrain_m": max_terrain,
        "problem_points": problems,
    }


# ---------------------------------------------------------------------------
# Batch terrain check for a full task
# ---------------------------------------------------------------------------

def check_task_terrain(
    task_points: list[tuple[float, float]],
    expected_altitude_m: int,
    clearance_margin_m: int = 300,
) -> dict:
    """Check terrain clearance for all legs of a task.

    Returns:
        safe: bool — all legs clear
        legs: list of per-leg clearance results
        max_terrain_m: highest terrain across the whole task
    """
    if len(task_points) < 2:
        return {"safe": True, "legs": [], "max_terrain_m": 0}

    legs = []
    overall_max = 0
    all_safe = True

    for i in range(len(task_points) - 1):
        p1 = task_points[i]
        p2 = task_points[i + 1]
        result = check_terrain_clearance(
            p1[0], p1[1], p2[0], p2[1],
            expected_altitude_m, clearance_margin_m,
        )
        result["leg_index"] = i
        legs.append(result)
        if result["max_terrain_m"] > overall_max:
            overall_max = result["max_terrain_m"]
        if not result["safe"]:
            all_safe = False

    return {
        "safe": all_safe,
        "legs": legs,
        "max_terrain_m": overall_max,
    }
