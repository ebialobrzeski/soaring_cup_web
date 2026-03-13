"""
Airspace data service — OpenAIP fetch, NOTAM integration, conflict detection.

Responsibilities:
- Fetch airspace polygons from OpenAIP (European airspace)
- Fetch active NOTAMs from the ICAO NOTAM API for a given date/area
- Detect conflicts between task legs and airspace boundaries
- Apply per-pilot safety buffers (conservative / standard / aggressive)
- Cache airspace snapshots in PostgreSQL with 24-hour TTL
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import OPENAIP_API_KEY, ICAO_API_KEY

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

OPENAIP_BASE_URL = "https://api.core.openaip.net/api"
ICAO_NOTAM_URL = "https://applications.icao.int/dataservices/api/notams-realtime-list"

SAFETY_BUFFERS_KM: dict[str, float] = {
    "conservative": 2.0,
    "standard": 0.5,
    "aggressive": 0.0,
}

# Airspace classes that may require transponder or flight plan
TRANSPONDER_REQUIRED_CLASSES = {"C", "D"}
FLIGHT_PLAN_REQUIRED_CLASSES = {"C"}
CONTROLLED_CLASSES = {"C", "D", "E"}

AIRSPACE_CACHE_TTL_HOURS = 24


# ── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class AirspaceZone:
    """A single airspace polygon with metadata."""
    name: str
    airspace_class: str          # ICAO class: A–G, or special types
    type: str                    # e.g. 'CTR', 'TMA', 'RESTRICTED', 'DANGER', 'PROHIBITED'
    lower_limit_ft: int          # lower vertical bound in feet MSL
    upper_limit_ft: int          # upper vertical bound in feet MSL
    polygon: list[tuple[float, float]]  # list of (lat, lon) pairs forming the boundary
    requires_transponder: bool = False
    requires_flight_plan: bool = False
    country: str = ""


@dataclass
class NotamEntry:
    """A single NOTAM affecting a geographic area."""
    notam_id: str
    location: str                # ICAO location indicator
    effective_start: datetime
    effective_end: datetime
    text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_nm: Optional[float] = None   # affected radius in nautical miles
    lower_limit_ft: Optional[int] = None
    upper_limit_ft: Optional[int] = None


@dataclass
class AirspaceConflict:
    """A detected conflict between a task leg and an airspace zone or NOTAM."""
    zone_name: str
    zone_type: str               # 'CTR', 'RESTRICTED', 'NOTAM', etc.
    airspace_class: str
    leg_index: int               # which task leg (0-based)
    requires_transponder: bool
    requires_flight_plan: bool
    is_notam: bool = False
    notam_id: Optional[str] = None
    suggestion: str = ""         # 'avoid' | 'accept' | 'check NOTAM'


@dataclass
class AirspaceCheckResult:
    """Summary of all airspace checks for a proposed task."""
    conflicts: list[AirspaceConflict] = field(default_factory=list)
    has_blocking_conflict: bool = False   # True if restricted/prohibited zone hit
    zones_in_area: list[AirspaceZone] = field(default_factory=list)
    notams_in_area: list[NotamEntry] = field(default_factory=list)


# ── Bounding Box Helpers ────────────────────────────────────────────────────

def _bbox_for_points(
    points: list[tuple[float, float]], buffer_km: float = 20.0
) -> tuple[float, float, float, float]:
    """Return (min_lat, min_lon, max_lat, max_lon) with buffer around points."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    # ~0.009° per km latitude, adjust lon for latitude
    avg_lat = sum(lats) / len(lats)
    lat_buf = buffer_km * 0.009
    lon_buf = buffer_km * 0.009 / max(math.cos(math.radians(avg_lat)), 0.1)
    return (
        min(lats) - lat_buf,
        min(lons) - lon_buf,
        max(lats) + lat_buf,
        max(lons) + lon_buf,
    )


def _bbox_hash(bbox: tuple[float, float, float, float], flight_date: date) -> str:
    """Deterministic hash for cache key."""
    raw = f"{bbox[0]:.2f},{bbox[1]:.2f},{bbox[2]:.2f},{bbox[3]:.2f},{flight_date.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── OpenAIP Integration ─────────────────────────────────────────────────────

def fetch_airspace_from_openaip(
    bbox: tuple[float, float, float, float],
) -> list[AirspaceZone]:
    """
    Fetch airspace polygons from OpenAIP for the given bounding box.

    Args:
        bbox: (min_lat, min_lon, max_lat, max_lon)

    Returns:
        List of AirspaceZone objects.
    """
    if not OPENAIP_API_KEY:
        logger.warning("OPENAIP_API_KEY not configured — skipping airspace fetch")
        return []

    min_lat, min_lon, max_lat, max_lon = bbox
    zones: list[AirspaceZone] = []

    try:
        page = 1
        while True:
            resp = requests.get(
                f"{OPENAIP_BASE_URL}/airspaces",
                params={
                    "pos": f"{(min_lat + max_lat) / 2},{(min_lon + max_lon) / 2}",
                    "dist": _bbox_diagonal_km(bbox) * 500,  # radius in metres
                    "page": page,
                    "limit": 100,
                },
                headers={
                    "x-openaip-api-key": OPENAIP_API_KEY,
                    "Accept": "application/json",
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                zone = _parse_openaip_airspace(item)
                if zone:
                    zones.append(zone)

            # Check if more pages exist
            total_count = data.get("totalCount", 0)
            if page * 100 >= total_count:
                break
            page += 1

        logger.info("Fetched %d airspace zones from OpenAIP", len(zones))

    except requests.RequestException as exc:
        logger.error("OpenAIP API error: %s", exc)

    return zones


def _bbox_diagonal_km(bbox: tuple[float, float, float, float]) -> float:
    """Approximate diagonal distance of a bbox in km."""
    min_lat, min_lon, max_lat, max_lon = bbox
    dlat = max_lat - min_lat
    dlon = max_lon - min_lon
    avg_lat = (min_lat + max_lat) / 2
    km_lat = dlat * 111.32
    km_lon = dlon * 111.32 * math.cos(math.radians(avg_lat))
    return math.sqrt(km_lat ** 2 + km_lon ** 2)


def _parse_openaip_airspace(item: dict) -> Optional[AirspaceZone]:
    """Parse a single OpenAIP airspace JSON object into an AirspaceZone."""
    try:
        name = item.get("name", "Unknown")
        icao_class = str(item.get("icaoClass", 0))
        # OpenAIP uses numeric class codes: 0=A, 1=B, ..., 8=SUA
        class_map = {
            "0": "A", "1": "B", "2": "C", "3": "D", "4": "E",
            "5": "F", "6": "G", "7": "SPECIAL", "8": "OTHER",
        }
        airspace_class = class_map.get(icao_class, icao_class)

        # Type classification
        atype = str(item.get("type", 0))
        type_map = {
            "0": "OTHER", "1": "RESTRICTED", "2": "DANGER", "3": "PROHIBITED",
            "4": "CTR", "5": "TMA", "6": "TMA", "7": "OTHER",
            "8": "FIR", "9": "UIR", "10": "ADIZ", "11": "ATZ",
            "12": "MATZ", "13": "AIRWAY", "14": "MTR", "15": "ALERT",
            "16": "WARNING", "17": "PROTECTED", "18": "HTZ", "19": "GLIDER_SECTOR",
            "20": "TRP", "21": "TIZ", "22": "TIA", "23": "MTA",
            "24": "CTA", "25": "ACC_SECTOR", "26": "AERIAL_SPORTING",
            "27": "OVERFLIGHT_RESTRICTION", "28": "RMZ", "29": "TMZ",
        }
        zone_type = type_map.get(atype, "OTHER")

        # Parse geometry
        geometry = item.get("geometry", {})
        coords_raw = geometry.get("coordinates", [[]])
        # GeoJSON polygon: first ring is the outer boundary
        if geometry.get("type") == "Polygon" and coords_raw:
            polygon = [(c[1], c[0]) for c in coords_raw[0]]  # GeoJSON is [lon, lat]
        else:
            return None

        # Parse altitude limits
        lower_limit = item.get("lowerLimit", {})
        upper_limit = item.get("upperLimit", {})
        lower_ft = _parse_altitude_ft(lower_limit)
        upper_ft = _parse_altitude_ft(upper_limit)

        country = item.get("country", "")

        return AirspaceZone(
            name=name,
            airspace_class=airspace_class,
            type=zone_type,
            lower_limit_ft=lower_ft,
            upper_limit_ft=upper_ft,
            polygon=polygon,
            requires_transponder=airspace_class in TRANSPONDER_REQUIRED_CLASSES,
            requires_flight_plan=airspace_class in FLIGHT_PLAN_REQUIRED_CLASSES,
            country=country,
        )
    except (KeyError, ValueError, TypeError) as exc:
        logger.debug("Skipping malformed OpenAIP airspace entry: %s", exc)
        return None


def _parse_altitude_ft(limit: dict) -> int:
    """Convert an OpenAIP altitude limit to feet MSL."""
    value = limit.get("value", 0)
    unit = limit.get("unit", 0)  # 0=feet, 1=meters, 6=FL
    reference = limit.get("referenceDatum", 0)  # 0=GND, 1=MSL, 2=STD

    if unit == 1:  # metres → feet
        value = int(value * 3.28084)
    elif unit == 6:  # flight level
        value = int(value) * 100

    return int(value)


# ── ICAO NOTAM Integration ──────────────────────────────────────────────────

def fetch_notams(
    bbox: tuple[float, float, float, float],
    flight_date: date,
) -> list[NotamEntry]:
    """
    Fetch active NOTAMs from the ICAO API for a bounding box and date.

    Args:
        bbox: (min_lat, min_lon, max_lat, max_lon)
        flight_date: The date of the planned flight.

    Returns:
        List of relevant NotamEntry objects.
    """
    if not ICAO_API_KEY:
        logger.warning("ICAO_API_KEY not configured — skipping NOTAM fetch")
        return []

    min_lat, min_lon, max_lat, max_lon = bbox
    notams: list[NotamEntry] = []

    try:
        # ICAO API expects locations or a geographic filter
        resp = requests.get(
            ICAO_NOTAM_URL,
            params={
                "api_key": ICAO_API_KEY,
                "format": "json",
                "Rone": f"{min_lat},{min_lon},{max_lat},{max_lon}",
                "type": "R",  # area-based query
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data if isinstance(data, list) else []:
            notam = _parse_notam(item, flight_date)
            if notam:
                notams.append(notam)

        logger.info(
            "Fetched %d active NOTAMs for %s", len(notams), flight_date.isoformat()
        )

    except requests.RequestException as exc:
        logger.error("ICAO NOTAM API error: %s", exc)

    return notams


def _parse_notam(item: dict, flight_date: date) -> Optional[NotamEntry]:
    """Parse a single NOTAM JSON entry; return None if not active on flight_date."""
    try:
        start_str = item.get("startdate", "")
        end_str = item.get("enddate", "")

        if start_str:
            effective_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        else:
            return None

        if end_str and end_str.upper() != "PERM":
            effective_end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        else:
            # Permanent NOTAM — treat as far future
            effective_end = datetime(2099, 12, 31, tzinfo=timezone.utc)

        # Check if NOTAM is active on the flight date
        flight_start = datetime(
            flight_date.year, flight_date.month, flight_date.day,
            tzinfo=timezone.utc,
        )
        flight_end = flight_start + timedelta(days=1)

        if effective_end < flight_start or effective_start > flight_end:
            return None

        # Parse location
        lat = item.get("latitude")
        lon = item.get("longitude")
        radius_raw = item.get("radius")
        radius_nm = float(radius_raw) if radius_raw else None

        return NotamEntry(
            notam_id=item.get("id", item.get("key", "UNKNOWN")),
            location=item.get("location", ""),
            effective_start=effective_start,
            effective_end=effective_end,
            text=item.get("message", item.get("all", "")),
            latitude=float(lat) if lat else None,
            longitude=float(lon) if lon else None,
            radius_nm=radius_nm,
        )
    except (ValueError, TypeError) as exc:
        logger.debug("Skipping malformed NOTAM: %s", exc)
        return None


# ── Geometry Helpers ─────────────────────────────────────────────────────────

def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance in km between two points."""
    R = 6371.0
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _point_in_polygon(
    lat: float, lon: float, polygon: list[tuple[float, float]]
) -> bool:
    """Ray-casting algorithm to test if a point is inside a polygon.

    Polygon points are (lat, lon) tuples.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]   # yi=lat, xi=lon
        yj, xj = polygon[j]   # yj=lat, xj=lon
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _segments_from_leg(
    start: tuple[float, float], end: tuple[float, float], step_km: float = 2.0
) -> list[tuple[float, float]]:
    """
    Sample points along a great-circle leg at approximately step_km intervals.
    Returns a list of (lat, lon) points including start and end.
    """
    dist = _haversine_km(start[0], start[1], end[0], end[1])
    if dist < 0.1:
        return [start, end]

    n_steps = max(2, int(dist / step_km) + 1)
    points = []
    for i in range(n_steps + 1):
        frac = i / n_steps
        # Linear interpolation (accurate enough for short segments)
        lat = start[0] + frac * (end[0] - start[0])
        lon = start[1] + frac * (end[1] - start[1])
        points.append((lat, lon))
    return points


# ── Conflict Detection ──────────────────────────────────────────────────────

def _check_point_airspace(
    point: tuple[float, float],
    point_index: int,
    zones: list[AirspaceZone],
    buffer_km: float,
    constraints: dict,
) -> list[AirspaceConflict]:
    """Check a single turnpoint against all airspace zones."""
    conflicts: list[AirspaceConflict] = []
    for zone in zones:
        hit = _point_in_polygon(point[0], point[1], zone.polygon)
        if not hit and buffer_km > 0:
            for poly_pt in zone.polygon:
                if _haversine_km(point[0], point[1], poly_pt[0], poly_pt[1]) < buffer_km:
                    hit = True
                    break
        if hit:
            suggestion = _suggest_action(zone, constraints)
            conflicts.append(AirspaceConflict(
                zone_name=zone.name,
                zone_type=zone.type,
                airspace_class=zone.airspace_class,
                leg_index=point_index,  # index of the turnpoint
                requires_transponder=zone.requires_transponder,
                requires_flight_plan=zone.requires_flight_plan,
                suggestion=suggestion,
            ))
    return conflicts


def _check_point_notams(
    point: tuple[float, float],
    point_index: int,
    notams: list[NotamEntry],
    buffer_km: float,
) -> list[AirspaceConflict]:
    """Check a single turnpoint against active NOTAMs."""
    conflicts: list[AirspaceConflict] = []
    for notam in notams:
        if notam.latitude is None or notam.longitude is None:
            continue
        radius_km = (notam.radius_nm or 5.0) * 1.852 + buffer_km
        if _haversine_km(point[0], point[1], notam.latitude, notam.longitude) < radius_km:
            conflicts.append(AirspaceConflict(
                zone_name=f"NOTAM {notam.notam_id}",
                zone_type="NOTAM",
                airspace_class="",
                leg_index=point_index,
                requires_transponder=False,
                requires_flight_plan=False,
                is_notam=True,
                notam_id=notam.notam_id,
                suggestion="check NOTAM",
            ))
    return conflicts


def check_leg_airspace_conflicts(
    leg_start: tuple[float, float],
    leg_end: tuple[float, float],
    leg_index: int,
    zones: list[AirspaceZone],
    buffer_km: float,
    constraints: dict,
) -> list[AirspaceConflict]:
    """
    Check a single task leg against all airspace zones.

    Args:
        leg_start: (lat, lon) of start point
        leg_end: (lat, lon) of end point
        leg_index: 0-based index of this leg in the task
        zones: List of AirspaceZone to check against
        buffer_km: Safety buffer in km from pilot profile
        constraints: Dict of airspace constraint toggles, e.g.:
            {
                "exclude_transponder": True,
                "exclude_flight_plan": True,
                "exclude_classes": ["C", "D"],
                "exclude_restricted": True,
                "exclude_danger": True,
                "exclude_prohibited": True,
            }

    Returns:
        List of AirspaceConflict for any conflicts found.
    """
    sample_points = _segments_from_leg(leg_start, leg_end)
    conflicts: list[AirspaceConflict] = []
    seen_zones: set[str] = set()  # Avoid duplicate conflicts per zone per leg

    for zone in zones:
        if zone.name in seen_zones:
            continue

        hit = False
        for point in sample_points:
            if _point_in_polygon(point[0], point[1], zone.polygon):
                hit = True
                break

            # Check buffer distance to polygon edges if buffer > 0
            if buffer_km > 0:
                for poly_pt in zone.polygon:
                    if _haversine_km(point[0], point[1], poly_pt[0], poly_pt[1]) < buffer_km:
                        hit = True
                        break
            if hit:
                break

        if not hit:
            continue

        seen_zones.add(zone.name)

        # Determine if this conflict is relevant given constraints
        suggestion = _suggest_action(zone, constraints)

        conflicts.append(AirspaceConflict(
            zone_name=zone.name,
            zone_type=zone.type,
            airspace_class=zone.airspace_class,
            leg_index=leg_index,
            requires_transponder=zone.requires_transponder,
            requires_flight_plan=zone.requires_flight_plan,
            suggestion=suggestion,
        ))

    return conflicts


def check_leg_notam_conflicts(
    leg_start: tuple[float, float],
    leg_end: tuple[float, float],
    leg_index: int,
    notams: list[NotamEntry],
    buffer_km: float,
) -> list[AirspaceConflict]:
    """Check a single task leg against active NOTAMs."""
    sample_points = _segments_from_leg(leg_start, leg_end)
    conflicts: list[AirspaceConflict] = []

    for notam in notams:
        if notam.latitude is None or notam.longitude is None:
            continue

        radius_km = (notam.radius_nm or 5.0) * 1.852  # NM to km
        total_radius = radius_km + buffer_km

        hit = False
        for point in sample_points:
            if _haversine_km(point[0], point[1], notam.latitude, notam.longitude) < total_radius:
                hit = True
                break

        if hit:
            conflicts.append(AirspaceConflict(
                zone_name=f"NOTAM {notam.notam_id}",
                zone_type="NOTAM",
                airspace_class="",
                leg_index=leg_index,
                requires_transponder=False,
                requires_flight_plan=False,
                is_notam=True,
                notam_id=notam.notam_id,
                suggestion="check NOTAM",
            ))

    return conflicts


def _suggest_action(zone: AirspaceZone, constraints: dict) -> str:
    """Determine the suggested action for a given conflict based on user constraints."""
    # Prohibited zones are always blocked — no user toggle can override
    if zone.type == "PROHIBITED":
        return "avoid"
    if zone.type == "RESTRICTED" and constraints.get("exclude_restricted", True):
        return "avoid"
    if zone.type == "DANGER" and constraints.get("exclude_danger", True):
        return "avoid"
    if zone.airspace_class in constraints.get("exclude_classes", []):
        return "avoid"
    if zone.requires_transponder and constraints.get("exclude_transponder", False):
        return "avoid"
    if zone.requires_flight_plan and constraints.get("exclude_flight_plan", False):
        return "avoid"
    return "accept"


# ── Cache Layer ──────────────────────────────────────────────────────────────

def _get_cached_airspace(
    db: Session, bbox: tuple[float, float, float, float], flight_date: date
) -> Optional[list[dict]]:
    """Retrieve cached airspace data if within TTL."""
    key = _bbox_hash(bbox, flight_date)
    row = db.execute(
        text("""
            SELECT data FROM airspace_cache
            WHERE bbox_hash = :key AND flight_date = :fd
              AND expires_at > NOW()
            ORDER BY created_at DESC LIMIT 1
        """),
        {"key": key, "fd": flight_date},
    ).fetchone()

    if row:
        logger.debug("Airspace cache hit for bbox_hash=%s", key)
        return row[0]  # JSONB column
    return None


def _store_airspace_cache(
    db: Session,
    bbox: tuple[float, float, float, float],
    flight_date: date,
    zones: list[AirspaceZone],
    notams: list[NotamEntry],
) -> None:
    """Store airspace + NOTAM data in cache with 24-hour TTL."""
    key = _bbox_hash(bbox, flight_date)
    payload = {
        "zones": [_zone_to_dict(z) for z in zones],
        "notams": [_notam_to_dict(n) for n in notams],
    }
    db.execute(
        text("""
            INSERT INTO airspace_cache (bbox_hash, flight_date, data, created_at, expires_at)
            VALUES (:key, :fd, :data, NOW(), NOW() + INTERVAL '24 hours')
            ON CONFLICT (bbox_hash, flight_date) DO UPDATE
              SET data = :data, created_at = NOW(), expires_at = NOW() + INTERVAL '24 hours'
        """),
        {"key": key, "fd": flight_date, "data": json.dumps(payload)},
    )
    db.commit()


def _zone_to_dict(zone: AirspaceZone) -> dict:
    """Serialize AirspaceZone to JSON-safe dict."""
    return {
        "name": zone.name,
        "airspace_class": zone.airspace_class,
        "type": zone.type,
        "lower_limit_ft": zone.lower_limit_ft,
        "upper_limit_ft": zone.upper_limit_ft,
        "polygon": zone.polygon,
        "requires_transponder": zone.requires_transponder,
        "requires_flight_plan": zone.requires_flight_plan,
        "country": zone.country,
    }


def _zone_from_dict(d: dict) -> AirspaceZone:
    """Deserialize AirspaceZone from a dict."""
    return AirspaceZone(
        name=d["name"],
        airspace_class=d["airspace_class"],
        type=d["type"],
        lower_limit_ft=d["lower_limit_ft"],
        upper_limit_ft=d["upper_limit_ft"],
        polygon=[tuple(p) for p in d["polygon"]],
        requires_transponder=d.get("requires_transponder", False),
        requires_flight_plan=d.get("requires_flight_plan", False),
        country=d.get("country", ""),
    )


def _notam_to_dict(notam: NotamEntry) -> dict:
    """Serialize NotamEntry to JSON-safe dict."""
    return {
        "notam_id": notam.notam_id,
        "location": notam.location,
        "effective_start": notam.effective_start.isoformat(),
        "effective_end": notam.effective_end.isoformat(),
        "text": notam.text,
        "latitude": notam.latitude,
        "longitude": notam.longitude,
        "radius_nm": notam.radius_nm,
    }


def _notam_from_dict(d: dict) -> NotamEntry:
    """Deserialize NotamEntry from a dict."""
    return NotamEntry(
        notam_id=d["notam_id"],
        location=d["location"],
        effective_start=datetime.fromisoformat(d["effective_start"]),
        effective_end=datetime.fromisoformat(d["effective_end"]),
        text=d["text"],
        latitude=d.get("latitude"),
        longitude=d.get("longitude"),
        radius_nm=d.get("radius_nm"),
    )


# ── Main Public API ─────────────────────────────────────────────────────────

def get_airspace_data(
    db: Session,
    task_points: list[tuple[float, float]],
    flight_date: date,
    buffer_km: float = 20.0,
) -> tuple[list[AirspaceZone], list[NotamEntry]]:
    """
    Fetch airspace zones and NOTAMs for the area around the task.
    Uses cache when available.

    Args:
        db: SQLAlchemy session (from get_db())
        task_points: List of (lat, lon) turnpoints defining the task
        flight_date: Planned flight date
        buffer_km: Extra buffer around the task area for airspace fetch

    Returns:
        Tuple of (zones, notams)
    """
    bbox = _bbox_for_points(task_points, buffer_km)

    # Warn when operating outside the well-covered European region
    if not _bbox_in_europe(bbox):
        logger.warning(
            "Task area is outside the primary European OpenAIP coverage region. "
            "Airspace data may be incomplete — no SkyVector fallback is available."
        )

    # Try cache first
    cached = _get_cached_airspace(db, bbox, flight_date)
    if cached:
        zones = [_zone_from_dict(z) for z in cached.get("zones", [])]
        notams = [_notam_from_dict(n) for n in cached.get("notams", [])]
        return zones, notams

    # Fetch fresh data
    zones = fetch_airspace_from_openaip(bbox)
    notams = fetch_notams(bbox, flight_date)

    # Cache the results
    try:
        _store_airspace_cache(db, bbox, flight_date, zones, notams)
    except Exception as exc:
        logger.warning("Failed to cache airspace data: %s", exc)
        db.rollback()

    return zones, notams


def check_task_airspace(
    db: Session,
    task_points: list[tuple[float, float]],
    flight_date: date,
    safety_profile: str = "standard",
    constraints: Optional[dict] = None,
    prefetched_zones: Optional[tuple] = None,
) -> AirspaceCheckResult:
    """
    Full airspace check for a proposed task.

    Args:
        db: SQLAlchemy session
        task_points: Ordered list of (lat, lon) turnpoints
        flight_date: Planned flight date
        safety_profile: 'conservative' | 'standard' | 'aggressive'
        constraints: Airspace constraint toggles dict
        prefetched_zones: Optional (zones, notams) tuple to skip API fetch.
            When provided, zones/notams are used directly instead of calling
            get_airspace_data.  This avoids redundant API calls when the
            optimizer checks many candidate routes against the same area.

    Returns:
        AirspaceCheckResult with all conflicts and metadata.
    """
    if constraints is None:
        constraints = {
            "exclude_transponder": False,
            "exclude_flight_plan": False,
            "exclude_classes": [],
            "exclude_restricted": True,
            "exclude_danger": True,
            "exclude_prohibited": True,
        }

    buffer_km = SAFETY_BUFFERS_KM.get(safety_profile, 0.5)
    if prefetched_zones is not None:
        zones, notams = prefetched_zones
    else:
        zones, notams = get_airspace_data(db, task_points, flight_date)

    all_conflicts: list[AirspaceConflict] = []
    has_blocking = False

    # Check each turnpoint individually
    for idx, tp in enumerate(task_points):
        tp_conflicts = _check_point_airspace(tp, idx, zones, buffer_km, constraints)
        all_conflicts.extend(tp_conflicts)
        tp_notam_conflicts = _check_point_notams(tp, idx, notams, buffer_km)
        all_conflicts.extend(tp_notam_conflicts)

    # Check each leg between consecutive turnpoints
    for i in range(len(task_points) - 1):
        leg_start = task_points[i]
        leg_end = task_points[i + 1]

        # Check static airspace
        airspace_conflicts = check_leg_airspace_conflicts(
            leg_start, leg_end, i, zones, buffer_km, constraints
        )
        all_conflicts.extend(airspace_conflicts)

        # Check NOTAMs
        notam_conflicts = check_leg_notam_conflicts(
            leg_start, leg_end, i, notams, buffer_km
        )
        all_conflicts.extend(notam_conflicts)

    # Determine if any conflicts are blocking
    for conflict in all_conflicts:
        if conflict.suggestion == "avoid":
            has_blocking = True
            break

    return AirspaceCheckResult(
        conflicts=all_conflicts,
        has_blocking_conflict=has_blocking,
        zones_in_area=zones,
        notams_in_area=notams,
    )


# ── Airspace Scoring for Optimizer ──────────────────────────────────────────

# Penalty weights used to convert conflicts into a 0–100 score.
_PENALTY = {
    "PROHIBITED": 100,
    "RESTRICTED": 40,
    "DANGER": 30,
    "NOTAM": 20,
    "CTR": 15,
    "TMA": 10,
}


def compute_airspace_score(result: AirspaceCheckResult) -> int:
    """Return an airspace-safety score (0–100) for optimizer route ranking.

    100 = completely clear, 0 = severe conflicts.  The score is computed by
    deducting penalties for each conflict (capped so it never goes below 0).
    """
    if not result.conflicts:
        return 100

    total_penalty = 0
    for c in result.conflicts:
        total_penalty += _PENALTY.get(c.zone_type, 5)

    return max(0, 100 - total_penalty)


# ── Region Awareness ────────────────────────────────────────────────────────

# OpenAIP covers most of Europe and many other regions.  The AI Task Planner
# specification mentions SkyVector as a fallback for non-European airspace,
# but SkyVector does not expose a public REST API.  The helper below detects
# whether a bounding box sits inside the well-covered European region and logs
# a warning when it does not, so callers know coverage may be reduced.

_EUROPE_BBOX = (-12.0, 33.0, 45.0, 72.0)  # (min_lon, min_lat, max_lon, max_lat)


def _bbox_in_europe(bbox: tuple[float, float, float, float]) -> bool:
    """Return True if the entire bbox falls within Europe."""
    min_lat, min_lon, max_lat, max_lon = bbox
    return (
        min_lon >= _EUROPE_BBOX[0]
        and min_lat >= _EUROPE_BBOX[1]
        and max_lon <= _EUROPE_BBOX[2]
        and max_lat <= _EUROPE_BBOX[3]
    )
