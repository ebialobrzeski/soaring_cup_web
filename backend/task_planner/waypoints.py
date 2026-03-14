"""Waypoint discovery — finds reachable towns, cities, and airports for AI route planning.

Provides the AI model with a structured list of potential turnpoints within
the task area, including nearby weather context for each.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import requests as _requests
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Waypoint:
    """A potential turnpoint with context for the AI."""
    name: str
    lat: float
    lon: float
    type: str  # "city", "town", "village", "airport"
    distance_km: float  # from takeoff
    bearing_deg: float  # from takeoff
    # Weather context (populated from nearest weather cell)
    thermal_index: Optional[float] = None
    wind_speed_kts: Optional[float] = None
    wind_dir: Optional[int] = None
    cloud_base_ft: Optional[int] = None
    # Airport-specific
    icao: Optional[str] = None
    has_runway: bool = False

    def summary_line(self) -> str:
        """Compact text line for the AI prompt."""
        parts = [
            f"{self.name} ({self.type})",
            f"{self.lat:.4f}N/{self.lon:.4f}E",
            f"{self.distance_km:.0f}km",
            f"{self.bearing_deg:.0f}°",
        ]
        if self.icao:
            parts[0] = f"{self.name} [{self.icao}] ({self.type})"
        if self.thermal_index is not None:
            label = "strong" if self.thermal_index >= 7 else "moderate" if self.thermal_index >= 4 else "weak"
            parts.append(f"thermal={label}({self.thermal_index:.1f})")
        if self.wind_speed_kts is not None and self.wind_dir is not None:
            parts.append(f"wind={self.wind_dir:.0f}°@{self.wind_speed_kts:.0f}kt")
        if self.cloud_base_ft is not None:
            parts.append(f"CB={self.cloud_base_ft}ft")
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# Geometry helpers (duplicated from optimizer to avoid circular imports)
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
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ---------------------------------------------------------------------------
# Airport discovery
# ---------------------------------------------------------------------------

def fetch_nearby_airports(
    db: Session,
    takeoff_lat: float,
    takeoff_lon: float,
    max_range_km: float,
) -> list[Waypoint]:
    """Query the airports table for active airports within range."""
    # Use a generous bounding box in SQL, then filter precisely in Python
    deg_margin = max_range_km / 111.0
    rows = db.execute(
        text("""
            SELECT id, "icaoCode", name, latitude, longitude, "runwayDirection"
            FROM airports
            WHERE "isActive" = true
              AND latitude  BETWEEN :min_lat AND :max_lat
              AND longitude BETWEEN :min_lon AND :max_lon
        """),
        {
            "min_lat": takeoff_lat - deg_margin,
            "max_lat": takeoff_lat + deg_margin,
            "min_lon": takeoff_lon - deg_margin * 1.5,
            "max_lon": takeoff_lon + deg_margin * 1.5,
        },
    ).fetchall()

    waypoints: list[Waypoint] = []
    for row in rows:
        lat, lon = row[3], row[4]
        dist = _haversine(takeoff_lat, takeoff_lon, lat, lon)
        if dist > max_range_km or dist < 3.0:  # skip takeoff airport itself
            continue
        waypoints.append(Waypoint(
            name=row[2],
            lat=lat,
            lon=lon,
            type="airport",
            distance_km=round(dist, 1),
            bearing_deg=round(_bearing(takeoff_lat, takeoff_lon, lat, lon), 0),
            icao=row[1] or None,
            has_runway=bool(row[5]),
        ))

    waypoints.sort(key=lambda w: w.distance_km)
    logger.info("Found %d airports within %.0fkm of takeoff", len(waypoints), max_range_km)
    return waypoints


# ---------------------------------------------------------------------------
# Supplement: fetch airfields / landing strips from OpenAIP live API
# ---------------------------------------------------------------------------

def _fetch_openaip_airfields(
    takeoff_lat: float,
    takeoff_lon: float,
    max_range_km: float,
) -> list[Waypoint]:
    """Fetch additional airfields / outlandings from OpenAIP that may not be
    in the local airports database (grass strips, glider sites, etc.)."""
    from backend.services.waypoint_generation_service import query_openaip_aviation

    lat_delta = max_range_km / 111.0
    lon_delta = max_range_km / (111.0 * math.cos(math.radians(takeoff_lat)))

    try:
        legacy_wps = query_openaip_aviation(
            min_lat=takeoff_lat - lat_delta,
            max_lat=takeoff_lat + lat_delta,
            min_lon=takeoff_lon - lon_delta,
            max_lon=takeoff_lon + lon_delta,
            types=["airports", "outlandings"],
        )
    except Exception:
        logger.warning("OpenAIP airfield fetch failed", exc_info=True)
        return []

    waypoints: list[Waypoint] = []
    for lwp in legacy_wps:
        lat, lon = lwp.latitude, lwp.longitude
        dist = _haversine(takeoff_lat, takeoff_lon, lat, lon)
        if dist > max_range_km or dist < 3.0:
            continue
        waypoints.append(Waypoint(
            name=lwp.name,
            lat=lat,
            lon=lon,
            type="airport",
            distance_km=round(dist, 1),
            bearing_deg=round(_bearing(takeoff_lat, takeoff_lon, lat, lon), 0),
            icao=lwp.description if lwp.description else None,
            has_runway=getattr(lwp, "style", 1) in (2, 4, 5),
        ))

    waypoints.sort(key=lambda w: w.distance_km)
    logger.info("OpenAIP returned %d airfields within %.0fkm", len(waypoints), max_range_km)
    return waypoints


# ---------------------------------------------------------------------------
# Town/city discovery via Overpass (OSM)
# ---------------------------------------------------------------------------

def fetch_nearby_towns(
    takeoff_lat: float,
    takeoff_lon: float,
    max_range_km: float,
    min_place_type: str = "town",
) -> list[Waypoint]:
    """Query OpenStreetMap for cities and towns within range.

    Args:
        min_place_type: Minimum settlement size to include.
            "city" = only cities
            "town" = cities + towns
            "village" = cities + towns + villages
    """
    place_types = {"city", "town"}
    if min_place_type == "village":
        place_types.add("village")
    elif min_place_type == "city":
        place_types = {"city"}

    place_filter = "|".join(sorted(place_types))

    deg_margin = max_range_km / 111.0
    bbox = (
        f"{takeoff_lat - deg_margin:.4f},"
        f"{takeoff_lon - deg_margin * 1.5:.4f},"
        f"{takeoff_lat + deg_margin:.4f},"
        f"{takeoff_lon + deg_margin * 1.5:.4f}"
    )

    query = (
        f'[out:json][timeout:15];'
        f'(node["place"~"^({place_filter})$"]({bbox}););'
        f'out body;'
    )

    try:
        resp = _requests.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=15,
            headers={"User-Agent": "GlidePlan/1.0 task-planner"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("Overpass town lookup failed", exc_info=True)
        return []

    waypoints: list[Waypoint] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue
        lat, lon = el["lat"], el["lon"]
        dist = _haversine(takeoff_lat, takeoff_lon, lat, lon)
        if dist > max_range_km or dist < 3.0:
            continue
        place_type = tags.get("place", "town")
        waypoints.append(Waypoint(
            name=name,
            lat=lat,
            lon=lon,
            type=place_type,
            distance_km=round(dist, 1),
            bearing_deg=round(_bearing(takeoff_lat, takeoff_lon, lat, lon), 0),
        ))

    waypoints.sort(key=lambda w: w.distance_km)
    logger.info("Found %d towns/cities within %.0fkm of takeoff", len(waypoints), max_range_km)
    return waypoints


# ---------------------------------------------------------------------------
# Weather enrichment
# ---------------------------------------------------------------------------

def enrich_waypoints_with_weather(
    waypoints: list[Waypoint],
    weather_cells: list,
) -> None:
    """Assign nearest weather cell data to each waypoint (mutates in place)."""
    if not weather_cells:
        return
    for wp in waypoints:
        best_cell = None
        best_dist = float("inf")
        for cell in weather_cells:
            d = _haversine(wp.lat, wp.lon, cell.lat, cell.lon)
            if d < best_dist:
                best_dist = d
                best_cell = cell
        if best_cell:
            wp.thermal_index = best_cell.thermal_index
            wp.wind_speed_kts = best_cell.wind_speed_kts
            wp.wind_dir = best_cell.wind_dir
            wp.cloud_base_ft = best_cell.cloud_base_ft


# ---------------------------------------------------------------------------
# Fallback: generate waypoints via live APIs when none exist locally
# ---------------------------------------------------------------------------

def _generate_waypoints_fallback(
    db: Session,
    takeoff_lat: float,
    takeoff_lon: float,
    max_range_km: float,
) -> list[Waypoint]:
    """Call the waypoint generation service to fetch airports + towns from live APIs.

    Converts the legacy Waypoint objects returned by the generation service
    into the task-planner Waypoint format.
    """
    from backend.services.waypoint_generation_service import generate_waypoints

    # Build a bounding box from the takeoff point and max range
    lat_delta = max_range_km / 111.0
    lon_delta = max_range_km / (111.0 * math.cos(math.radians(takeoff_lat)))

    result = generate_waypoints(
        db,
        min_lat=takeoff_lat - lat_delta,
        max_lat=takeoff_lat + lat_delta,
        min_lon=takeoff_lon - lon_delta,
        max_lon=takeoff_lon + lon_delta,
        types=["airports", "cities", "towns"],
    )

    legacy_wps = result.get("waypoints", [])
    converted: list[Waypoint] = []
    for lwp in legacy_wps:
        lat = lwp.latitude
        lon = lwp.longitude
        dist = _haversine(takeoff_lat, takeoff_lon, lat, lon)
        if dist > max_range_km:
            continue
        # Infer type from CUP style: 2=grass, 4=gliding, 5=solid → airport
        wp_type = "airport" if getattr(lwp, "style", 1) in (2, 4, 5) else "town"
        converted.append(Waypoint(
            name=lwp.name,
            lat=lat,
            lon=lon,
            type=wp_type,
            distance_km=round(dist, 1),
            bearing_deg=round(_bearing(takeoff_lat, takeoff_lon, lat, lon), 0),
            icao=lwp.description if wp_type == "airport" and lwp.description else None,
        ))

    converted.sort(key=lambda w: w.distance_km)
    logger.info("Fallback generated %d waypoints from live APIs", len(converted))
    return converted


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def discover_waypoints(
    db: Session,
    takeoff_lat: float,
    takeoff_lon: float,
    target_distance_km: float,
    weather_cells: list,
    safety_profile: str = "standard",
) -> list[Waypoint]:
    """Discover all reachable waypoints for the AI to use when proposing routes.

    Returns a combined, deduplicated, weather-enriched list of airports and
    towns sorted by distance from takeoff.
    """
    # Range is roughly half the target distance (routes are closed circuits)
    # plus some margin for asymmetric routes
    if safety_profile == "conservative":
        max_range = target_distance_km * 0.45
    elif safety_profile == "aggressive":
        max_range = target_distance_km * 0.65
    else:
        max_range = target_distance_km * 0.55

    # Ensure minimum range for short tasks
    max_range = max(max_range, 25.0)

    # Never include villages — they flood the prompt with thousands of entries.
    # Cities and towns provide sufficient turnpoint density for any task distance.
    min_place = "town"

    airports = fetch_nearby_airports(db, takeoff_lat, takeoff_lon, max_range)

    # Supplement with OpenAIP airfields (grass strips, glider sites, outlandings)
    openaip_airports = _fetch_openaip_airfields(takeoff_lat, takeoff_lon, max_range)
    # Merge: keep OpenAIP airfields that aren't duplicates of DB airports (within 2km)
    for oap in openaip_airports:
        duplicate = any(
            _haversine(oap.lat, oap.lon, ap.lat, ap.lon) < 2.0
            for ap in airports
        )
        if not duplicate:
            airports.append(oap)

    towns = fetch_nearby_towns(takeoff_lat, takeoff_lon, max_range, min_place_type=min_place)

    # Deduplicate: if a town is within 3km of an airport, keep only the airport
    deduped_towns: list[Waypoint] = []
    for town in towns:
        too_close = any(
            _haversine(town.lat, town.lon, ap.lat, ap.lon) < 3.0
            for ap in airports
        )
        if not too_close:
            deduped_towns.append(town)

    all_waypoints = airports + deduped_towns
    all_waypoints.sort(key=lambda w: w.distance_km)

    # Fallback: if no waypoints found via DB/Overpass, generate from live APIs
    if not all_waypoints:
        logger.warning(
            "No waypoints found within %.0fkm of takeoff — falling back to live generation",
            max_range,
        )
        all_waypoints = _generate_waypoints_fallback(
            db, takeoff_lat, takeoff_lon, max_range,
        )

    enrich_waypoints_with_weather(all_waypoints, weather_cells)

    logger.info(
        "Discovered %d waypoints (%d airports + %d towns) within %.0fkm",
        len(all_waypoints), len(airports), len(deduped_towns), max_range,
    )
    return all_waypoints
