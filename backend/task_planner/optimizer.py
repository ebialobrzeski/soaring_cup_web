"""Task optimizer — candidate route generation, scoring, and selection.

Implements the objective function from AI_TASK_PLANNER.md:
  1. Distance match (±5% of target)
  2. Thermal coverage (BL ≥ 1200m, positive thermal index)
  3. Wind exposure (minimize headwind on longest leg)
  4. Terrain clearance
  5. Airspace safety
  6. Landable field proximity (best-effort)

Algorithm:
  - Generate candidate turnpoint sets geometrically (radial sweep from takeoff)
  - Score each candidate with weighted criteria
  - Return top 5 for LLM narrative
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import requests as _requests

logger = logging.getLogger(__name__)

# Overpass API for reverse-geocoding turnpoints to nearby towns
_OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Nominatim for forward-geocoding place names from custom instructions
_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TaskLeg:
    from_name: str
    from_lat: float
    from_lon: float
    to_name: str
    to_lat: float
    to_lon: float
    distance_km: float
    bearing: float
    thermal_quality: Optional[float] = None
    wind_component_kts: Optional[float] = None  # positive = headwind
    terrain_clearance: Optional[dict] = None
    airspace_conflicts: int = 0


def _format_wind_exposure(wind_component_kts: Optional[float]) -> Optional[str]:
    """Format wind component as a human-readable string for the frontend."""
    if wind_component_kts is None:
        return None
    hw = wind_component_kts
    abs_hw = abs(hw)
    if abs_hw < 1:
        return "calm"
    if hw > 0:
        return f"↑ {abs_hw:.0f}kt HW"
    return f"↓ {abs_hw:.0f}kt TW"


@dataclass
class CandidateRoute:
    legs: list[TaskLeg] = field(default_factory=list)
    total_distance_km: float = 0.0
    score: float = 0.0
    description: str = ""
    turnpoints: list[tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_distance_km": round(self.total_distance_km, 1),
            "score": round(self.score, 1),
            "description": self.description,
            "turnpoints": [{"lat": t[0], "lon": t[1]} for t in self.turnpoints],
            "legs": [
                {
                    "from": leg.from_name,
                    "to": leg.to_name,
                    "from_lat": leg.from_lat,
                    "from_lon": leg.from_lon,
                    "to_lat": leg.to_lat,
                    "to_lon": leg.to_lon,
                    "distance_km": round(leg.distance_km, 1),
                    "bearing": round(leg.bearing, 0),
                    "thermal_quality": leg.thermal_quality,
                    "wind_component_kts": leg.wind_component_kts,
                    "wind_exposure": _format_wind_exposure(leg.wind_component_kts),
                    "airspace_conflicts": leg.airspace_conflicts,
                }
                for leg in self.legs
            ],
        }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _max_distance_from_home(
    points: list[tuple[float, float]],
    home_lat: float,
    home_lon: float,
) -> float:
    """Return the maximum distance (km) any route point is from home."""
    return max(
        _haversine(home_lat, home_lon, p[0], p[1])
        for p in points
    )


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


def calculate_wind_components(
    wind_dir: int,
    wind_speed: float,
    leg_bearing: float,
) -> dict:
    """Decompose wind into headwind/tailwind/crosswind for a leg bearing."""
    angle_diff = math.radians(wind_dir - leg_bearing)
    headwind = wind_speed * math.cos(angle_diff)
    crosswind = wind_speed * math.sin(angle_diff)
    return {
        "headwind": round(headwind, 1),
        "tailwind": round(-headwind, 1) if headwind < 0 else 0.0,
        "crosswind": round(abs(crosswind), 1),
    }


# ---------------------------------------------------------------------------
# Candidate generation — radial sweep + triangle/out-and-return
# ---------------------------------------------------------------------------

def _generate_out_and_return(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    n_bearings: int = 12,
) -> list[list[tuple[float, float]]]:
    """Generate out-and-return candidates at different bearings."""
    half_dist = target_km / 2.0
    routes = []
    for i in range(n_bearings):
        bearing = (360.0 / n_bearings) * i
        tp = _destination(takeoff_lat, takeoff_lon, bearing, half_dist)
        routes.append([(takeoff_lat, takeoff_lon), tp, (takeoff_lat, takeoff_lon)])
    return routes


def _generate_triangles(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    n_rotations: int = 12,
) -> list[list[tuple[float, float]]]:
    """Generate equilateral triangle candidates at different orientations."""
    # Equilateral triangle: each leg ≈ target/3
    leg_km = target_km / 3.0
    routes = []
    for i in range(n_rotations):
        base_bearing = (360.0 / n_rotations) * i
        tp1 = _destination(takeoff_lat, takeoff_lon, base_bearing, leg_km)
        tp2 = _destination(tp1[0], tp1[1], (base_bearing + 120) % 360, leg_km)
        routes.append([
            (takeoff_lat, takeoff_lon),
            tp1,
            tp2,
            (takeoff_lat, takeoff_lon),
        ])
    return routes


def _generate_fai_triangles(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    n_rotations: int = 12,
) -> list[list[tuple[float, float]]]:
    """Generate FAI triangle candidates (28% min leg)."""
    routes = []
    # FAI triangle: legs 28%, 36%, 36% of total
    for i in range(n_rotations):
        base_bearing = (360.0 / n_rotations) * i
        leg1_km = target_km * 0.36
        tp1 = _destination(takeoff_lat, takeoff_lon, base_bearing, leg1_km)
        # Second leg at ~100-130° turn
        tp2 = _destination(tp1[0], tp1[1], (base_bearing + 110) % 360, target_km * 0.36)
        routes.append([
            (takeoff_lat, takeoff_lon),
            tp1,
            tp2,
            (takeoff_lat, takeoff_lon),
        ])
    return routes


def _generate_sector_routes(
    takeoff_lat: float, takeoff_lon: float,
    dest_lat: Optional[float], dest_lon: Optional[float],
    target_km: float,
    n_candidates: int = 12,
) -> list[list[tuple[float, float]]]:
    """Generate routes between takeoff and destination with midpoint turnpoints."""
    if dest_lat is None or dest_lon is None:
        return []

    direct_dist = _haversine(takeoff_lat, takeoff_lon, dest_lat, dest_lon)
    if direct_dist < 5:
        return []  # same airport, use triangle/O&R instead

    # Generate routes with 1-2 turnpoints offset from the direct line
    routes = []
    mid_lat = (takeoff_lat + dest_lat) / 2
    mid_lon = (takeoff_lon + dest_lon) / 2
    direct_bearing = _bearing(takeoff_lat, takeoff_lon, dest_lat, dest_lon)

    for i in range(n_candidates):
        offset_bearing = (direct_bearing + 90) % 360
        # Vary the offset distance
        offset_km = (target_km - direct_dist) / 2 * (0.3 + 0.7 * (i / max(1, n_candidates - 1)))
        if i % 2 == 1:
            offset_bearing = (direct_bearing - 90 + 360) % 360

        tp = _destination(mid_lat, mid_lon, offset_bearing, offset_km)
        routes.append([
            (takeoff_lat, takeoff_lon),
            tp,
            (dest_lat, dest_lon),
        ])

    return routes


def generate_candidates(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    dest_lat: Optional[float] = None,
    dest_lon: Optional[float] = None,
    soaring_mode: str = "thermal",
) -> list[list[tuple[float, float]]]:
    """Generate all candidate turnpoint sets.

    Returns list of routes, each route being a list of (lat, lon) waypoints
    starting and ending at takeoff/destination.
    """
    candidates: list[list[tuple[float, float]]] = []

    same_airport = (
        dest_lat is None or dest_lon is None
        or _haversine(takeoff_lat, takeoff_lon, dest_lat, dest_lon) < 5
    )

    if same_airport:
        # Out-and-return + triangles
        candidates.extend(_generate_out_and_return(takeoff_lat, takeoff_lon, target_km, 8))
        candidates.extend(_generate_triangles(takeoff_lat, takeoff_lon, target_km, 6))
        candidates.extend(_generate_fai_triangles(takeoff_lat, takeoff_lon, target_km, 4))
    else:
        # Sector routes between airports + some triangles from takeoff
        candidates.extend(
            _generate_sector_routes(takeoff_lat, takeoff_lon, dest_lat, dest_lon, target_km, 12)
        )
        candidates.extend(_generate_triangles(takeoff_lat, takeoff_lon, target_km, 8))

    return candidates


# ---------------------------------------------------------------------------
# Preferred-waypoint candidate generation
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
        # Pick the closest result to the bias point
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


def _generate_waypoint_routes(
    takeoff_lat: float,
    takeoff_lon: float,
    target_km: float,
    waypoints: list[tuple[float, float]],
    dest_lat: Optional[float] = None,
    dest_lon: Optional[float] = None,
) -> list[list[tuple[float, float]]]:
    """Generate candidate routes that pass through specific waypoints.

    For each preferred waypoint, generates:
    - Out-and-return through that waypoint
    - Triangles using that waypoint as one turnpoint (8 rotations for TP2)
    """
    same_airport = (
        dest_lat is None or dest_lon is None
        or _haversine(takeoff_lat, takeoff_lon, dest_lat or 0, dest_lon or 0) < 5
    )
    finish = (dest_lat, dest_lon) if not same_airport else (takeoff_lat, takeoff_lon)
    routes: list[list[tuple[float, float]]] = []

    for wp in waypoints:
        wp_dist = _haversine(takeoff_lat, takeoff_lon, wp[0], wp[1])

        # Out-and-return through the waypoint
        if same_airport:
            routes.append([(takeoff_lat, takeoff_lon), wp, (takeoff_lat, takeoff_lon)])
        else:
            routes.append([(takeoff_lat, takeoff_lon), wp, finish])

        # Triangles: waypoint as TP1, generate TP2 at various bearings
        if same_airport:
            bearing_from_home = _bearing(takeoff_lat, takeoff_lon, wp[0], wp[1])
            remaining_dist = target_km - wp_dist
            for i in range(8):
                # Spread TP2 at angles relative to the wp→home bearing
                offset_angle = (360.0 / 8) * i
                tp2_bearing = (bearing_from_home + 90 + offset_angle) % 360
                tp2_dist = remaining_dist * 0.45  # roughly balance the triangle
                tp2 = _destination(wp[0], wp[1], tp2_bearing, max(tp2_dist, 10))
                routes.append([
                    (takeoff_lat, takeoff_lon),
                    wp,
                    tp2,
                    (takeoff_lat, takeoff_lon),
                ])

                # Also try wp as TP2 instead of TP1
                tp1_bearing = (bearing_from_home + offset_angle) % 360
                tp1_dist = (target_km - wp_dist) * 0.45
                tp1 = _destination(takeoff_lat, takeoff_lon, tp1_bearing, max(tp1_dist, 10))
                routes.append([
                    (takeoff_lat, takeoff_lon),
                    tp1,
                    wp,
                    (takeoff_lat, takeoff_lon),
                ])

    logger.info("Generated %d waypoint-based candidates for %d preferred waypoints",
                len(routes), len(waypoints))
    return routes


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _route_distance(points: list[tuple[float, float]]) -> float:
    """Calculate total route distance in km."""
    total = 0
    for i in range(len(points) - 1):
        total += _haversine(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1])
    return total


def _nearest_cell(lat: float, lon: float, cells: list) -> Optional[object]:
    """Find the nearest weather cell to a point."""
    best = None
    best_dist = float("inf")
    for c in cells:
        d = _haversine(lat, lon, c.lat, c.lon)
        if d < best_dist:
            best_dist = d
            best = c
    return best


def _estimate_time_window(
    leg_index: int,
    n_legs: int,
    takeoff_hour: float = 11.0,
    duration_hours: float = 4.0,
) -> str:
    """Estimate which time window a leg falls into based on flight progress."""
    progress = leg_index / max(1, n_legs)
    est_hour = takeoff_hour + progress * duration_hours
    if est_hour < 12:
        return "morning"
    elif est_hour < 15:
        return "midday"
    return "afternoon"


def _sample_leg_weather(
    p1: tuple[float, float],
    p2: tuple[float, float],
    weather_cells: list,
    timed_cells: Optional[dict] = None,
    time_window: Optional[str] = None,
    n_samples: int = 3,
) -> list:
    """Sample weather at multiple points along a leg.

    Returns list of nearest WeatherCell objects for evenly-spaced
    sample points along the leg (at 25%, 50%, 75% by default).
    Uses time-specific cells if available for temporal accuracy.
    """
    cells_to_search = weather_cells
    if timed_cells and time_window and time_window in timed_cells:
        tw_cells = timed_cells[time_window]
        if tw_cells:
            cells_to_search = tw_cells

    samples = []
    for i in range(1, n_samples + 1):
        frac = i / (n_samples + 1)
        lat = p1[0] + frac * (p2[0] - p1[0])
        lon = p1[1] + frac * (p2[1] - p1[1])
        cell = _nearest_cell(lat, lon, cells_to_search)
        if cell:
            samples.append(cell)
    return samples


def _average_wind_direction(weather_cells: list) -> Optional[float]:
    """Compute the prevailing wind direction from weather cells (vector average)."""
    sin_sum = 0.0
    cos_sum = 0.0
    count = 0
    for c in weather_cells:
        if c.wind_dir is not None and c.wind_speed_kts is not None and c.wind_speed_kts > 2:
            rad = math.radians(c.wind_dir)
            w = c.wind_speed_kts
            sin_sum += w * math.sin(rad)
            cos_sum += w * math.cos(rad)
            count += 1
    if count == 0:
        return None
    return (math.degrees(math.atan2(sin_sum, cos_sum)) + 360) % 360


def score_candidate(
    points: list[tuple[float, float]],
    target_km: float,
    weather_cells: list,
    airspace_result: Optional[dict] = None,
    terrain_result: Optional[dict] = None,
    safety_profile: str = "standard",
    timed_cells: Optional[dict] = None,
    takeoff_hour: float = 11.0,
    max_duration_hours: float = 4.0,
) -> CandidateRoute:
    """Score a single candidate route.

    Returns a CandidateRoute with score 0-100.

    Improvements over v1:
      - Samples weather at 3 points per leg instead of just midpoint
      - Uses time-bucketed weather cells (morning/midday/afternoon)
      - Penalises routes starting downwind (wind alignment score)
    """
    total_dist = _route_distance(points)
    n_total_legs = len(points) - 1

    # 1. Distance match (0-25 pts)
    dist_error = abs(total_dist - target_km) / target_km if target_km > 0 else 1.0
    if dist_error <= 0.05:
        distance_score = 25.0
    elif dist_error <= 0.10:
        distance_score = 20.0
    elif dist_error <= 0.20:
        distance_score = 15.0
    elif dist_error <= 0.30:
        distance_score = 10.0
    else:
        distance_score = max(0, 25 - dist_error * 50)

    # 2. Thermal coverage (0-30 pts) — multi-point sampling with time awareness
    thermal_score = 0.0
    thermal_legs = 0.0
    legs = []
    for i in range(n_total_legs):
        p1, p2 = points[i], points[i + 1]
        dist = _haversine(p1[0], p1[1], p2[0], p2[1])
        brng = _bearing(p1[0], p1[1], p2[0], p2[1])

        # Estimate time window for this leg
        tw = _estimate_time_window(i, n_total_legs, takeoff_hour, max_duration_hours)

        # Sample weather at 3 points along the leg (25%, 50%, 75%)
        sample_cells = _sample_leg_weather(p1, p2, weather_cells, timed_cells, tw)

        tq = None
        wind_comp = None
        leg_thermal_quality = 0.0

        if sample_cells:
            # Aggregate thermal quality across all samples
            good_samples = 0.0
            thermal_values = []
            wind_values = []

            for cell in sample_cells:
                bl_ok = cell.bl_height is not None and cell.bl_height >= 1200
                ti_ok = cell.thermal_index is not None and cell.thermal_index >= 3.0
                if bl_ok and ti_ok:
                    good_samples += 1.0
                    thermal_values.append(cell.thermal_index)
                elif bl_ok or ti_ok:
                    good_samples += 0.5
                    thermal_values.append(cell.thermal_index or 0)

                if cell.wind_speed_kts is not None and cell.wind_dir is not None:
                    wc = calculate_wind_components(cell.wind_dir, cell.wind_speed_kts, brng)
                    wind_values.append(wc["headwind"])

            # Leg thermal quality = fraction of good samples
            n_samples = len(sample_cells)
            leg_thermal_quality = good_samples / n_samples if n_samples else 0
            thermal_legs += leg_thermal_quality

            tq = round(sum(thermal_values) / len(thermal_values), 1) if thermal_values else None
            wind_comp = round(sum(wind_values) / len(wind_values), 1) if wind_values else None

        legs.append(TaskLeg(
            from_name=f"TP{i}" if i > 0 else "Takeoff",
            from_lat=p1[0], from_lon=p1[1],
            to_name=f"TP{i+1}" if i + 1 < n_total_legs else "Finish",
            to_lat=p2[0], to_lon=p2[1],
            distance_km=dist,
            bearing=brng,
            thermal_quality=tq,
            wind_component_kts=wind_comp,
        ))

    n_legs = len(legs) if legs else 1
    thermal_score = (thermal_legs / n_legs) * 30

    # 3. Wind exposure (0-20 pts) — reward longest leg downwind, penalise headwind
    wind_score = 20.0
    longest_leg = max(legs, key=lambda l: l.distance_km) if legs else None
    if longest_leg and longest_leg.wind_component_kts is not None:
        hw = longest_leg.wind_component_kts
        if hw > 15:
            wind_score = 2.0
        elif hw > 10:
            wind_score = 7.0
        elif hw > 5:
            wind_score = 12.0
        elif hw > 0:
            wind_score = 16.0
        # Tailwind on longest leg — this is ideal for asymmetric routes
        if hw < -5:
            wind_score = 20.0  # full marks for tailwind on longest leg

    # Wind alignment bonus: first leg into wind AND longest leg downwind
    wind_alignment_bonus = 0.0
    if safety_profile in ("conservative", "standard") and legs:
        avg_wind_dir = _average_wind_direction(weather_cells)
        if avg_wind_dir is not None:
            first_leg_bearing = legs[0].bearing
            # Angle between first leg and wind direction (wind comes FROM wind_dir)
            angle_diff = abs(first_leg_bearing - avg_wind_dir)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            # 0° = flying directly into wind (best), 180° = downwind start (worst)
            if angle_diff < 45:
                wind_alignment_bonus = 8.0  # flying into wind — strongly rewarded
            elif angle_diff < 90:
                wind_alignment_bonus = 3.0  # crosswind start
            elif angle_diff > 135:
                wind_alignment_bonus = -8.0  # downwind start — strongly penalised

            # Bonus for longest leg being downwind (asymmetric triangle advantage)
            if longest_leg:
                longest_bearing = longest_leg.bearing
                # Ideal: longest leg bearing ≈ wind_dir + 180° (flying with the wind)
                downwind_bearing = (avg_wind_dir + 180) % 360
                dw_diff = abs(longest_bearing - downwind_bearing)
                if dw_diff > 180:
                    dw_diff = 360 - dw_diff
                if dw_diff < 30:
                    wind_alignment_bonus += 7.0  # longest leg is nearly pure downwind
                elif dw_diff < 60:
                    wind_alignment_bonus += 4.0  # longest leg has strong downwind component
                elif dw_diff < 90:
                    wind_alignment_bonus += 1.0  # some downwind component

    # 3b. Airport proximity score (0-15 pts) — reward routes that keep pilot close to home
    proximity_bonus = 0.0
    if safety_profile in ("conservative", "standard") and len(points) >= 4:
        # Calculate max distance of any turnpoint from home
        home_lat, home_lon = points[0]
        tp_distances = [
            _haversine(home_lat, home_lon, p[0], p[1])
            for p in points[1:-1]
        ]
        if tp_distances:
            max_tp_dist = max(tp_distances)
            # Ratio: farthest turnpoint distance / half of target_km
            # For equilateral triangle (120km): each leg ~40km, TPs ~35-40km away → ratio ~0.65
            # For asymmetric (25/45/30): TP1 ~25km away → good, but TP2 ~45km → ratio ~0.75
            # Key: check if the CLOSEST turnpoint is much closer (asymmetric benefit)
            min_tp_dist = min(tp_distances)
            half_target = target_km / 2.0 if target_km > 0 else 1.0

            # Reward when nearest TP is close to home (asymmetric advantage)
            near_ratio = min_tp_dist / half_target
            if near_ratio < 0.45:
                proximity_bonus = 12.0  # nearest TP very close to home
            elif near_ratio < 0.55:
                proximity_bonus = 8.0
            elif near_ratio < 0.70:
                proximity_bonus = 4.0
            else:
                proximity_bonus = 0.0  # all TPs far from home (equilateral)

            # Extra penalty if farthest TP is very far from home
            far_ratio = max_tp_dist / half_target
            if far_ratio > 1.0:
                proximity_bonus -= 3.0

            if safety_profile == "conservative":
                proximity_bonus *= 1.5  # extra weight for conservative
            proximity_bonus = max(0.0, proximity_bonus)

    # 4. Terrain clearance (0-15 pts)
    terrain_score = 15.0
    if terrain_result:
        if not terrain_result.get("safe", True):
            terrain_score = 0.0
        elif terrain_result.get("max_terrain_m", 0) > 1500:
            terrain_score = 10.0

    # 5. Airspace safety (0-10 pts)
    airspace_score = 10.0
    if airspace_result:
        n_conflicts = len(airspace_result.get("conflicts", []))
        if airspace_result.get("has_blocking_conflict"):
            airspace_score = 0.0
        elif n_conflicts > 3:
            airspace_score = 3.0
        elif n_conflicts > 0:
            airspace_score = 7.0

    total_score = (distance_score + thermal_score + wind_score
                   + terrain_score + airspace_score + wind_alignment_bonus
                   + proximity_bonus)

    # 6. Route-type preference based on safety profile (bonus/penalty)
    is_out_and_return = (len(points) == 3 and points[0] == points[2])
    is_triangle = (len(points) >= 4 and points[0] == points[-1])

    route_type_bonus = 0.0
    if safety_profile in ("conservative", "standard"):
        if is_triangle:
            route_type_bonus = 15.0 if safety_profile == "conservative" else 10.0
            logger.debug("Triangle route +%.0f bonus (safety=%s)", route_type_bonus, safety_profile)
        elif is_out_and_return:
            route_type_bonus = -10.0 if safety_profile == "conservative" else -5.0
            logger.debug("Out-and-return %.0f penalty (safety=%s)", route_type_bonus, safety_profile)
    total_score += route_type_bonus

    # 7. Leg asymmetry bonus (0-15 pts) — directly reward triangles with unequal legs
    # Coefficient of variation (CV) of leg lengths: 0 for equilateral, ~0.25+ for asymmetric.
    # This is the primary differentiator when wind data is missing.
    asymmetry_bonus = 0.0
    if is_triangle and len(legs) >= 3 and safety_profile in ("conservative", "standard"):
        leg_dists = [l.distance_km for l in legs]
        mean_dist = sum(leg_dists) / len(leg_dists)
        if mean_dist > 0:
            variance = sum((d - mean_dist) ** 2 for d in leg_dists) / len(leg_dists)
            cv = math.sqrt(variance) / mean_dist
            if cv > 0.30:
                asymmetry_bonus = 15.0
            elif cv > 0.20:
                asymmetry_bonus = 12.0
            elif cv > 0.10:
                asymmetry_bonus = 8.0
            elif cv > 0.05:
                asymmetry_bonus = 4.0
            if safety_profile == "conservative":
                asymmetry_bonus *= 1.3
    total_score += asymmetry_bonus

    route = CandidateRoute(
        legs=legs,
        total_distance_km=total_dist,
        score=total_score,
        turnpoints=list(points),
    )

    # Build description
    tp_names = [f"({p[0]:.2f}, {p[1]:.2f})" for p in points[1:-1]] if len(points) > 2 else []
    if is_out_and_return:
        route.description = f"Out-and-return via {tp_names[0] if tp_names else '?'}, {total_dist:.0f}km"
    elif is_triangle:
        route.description = f"Triangle via {', '.join(tp_names)}, {total_dist:.0f}km"
    else:
        route.description = f"Task with {len(tp_names)} TP(s), {total_dist:.0f}km"

    logger.debug(
        "Scored route: %s | dist=%.1fkm | score=%.1f "
        "(dist=%.0f therm=%.0f wind=%.0f+align=%.0f prox=%.0f asym=%.0f terrain=%.0f airsp=%.0f type_bonus=%.0f)",
        route.description, total_dist, total_score,
        distance_score, thermal_score, wind_score, wind_alignment_bonus,
        proximity_bonus, asymmetry_bonus, terrain_score, airspace_score, route_type_bonus,
    )

    return route


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

# Leg-length ratios for asymmetric triangles by safety profile.
# Pattern: short upwind leg → long downwind leg → short return.
# Conservative keeps the pilot closer to home; aggressive allows longer upwind legs.
_ASYM_RATIOS: dict[str, list[tuple[float, float, float]]] = {
    "conservative": [
        (0.20, 0.50, 0.30),  # 20% upwind, 50% downwind, 30% return
        (0.25, 0.45, 0.30),
        (0.22, 0.48, 0.30),
    ],
    "standard": [
        (0.25, 0.45, 0.30),  # 25% upwind, 45% downwind, 30% return
        (0.28, 0.42, 0.30),
        (0.30, 0.40, 0.30),
    ],
    "aggressive": [
        (0.30, 0.40, 0.30),  # more balanced for aggressive pilots
        (0.33, 0.34, 0.33),  # nearly equilateral
        (0.35, 0.35, 0.30),
    ],
}


def _generate_wind_biased_triangles(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    wind_dir: Optional[float],
    safety_profile: str = "standard",
    n_rotations: int = 6,
) -> list[list[tuple[float, float]]]:
    """Generate asymmetric triangle candidates biased to start into the wind.

    Leg 1 (short) flies INTO the wind so the pilot stays close to home.
    Leg 2 (long) flies WITH the wind — the longest leg is safest downwind.
    Leg 3 (medium) returns to the airport.

    Example with 150km task and north wind (conservative):
      Leg 1: 30km north (into wind — short, stays close to home)
      Leg 2: 75km south (with tailwind — long, efficient)
      Leg 3: 45km north-east back to airport

    When wind_dir is None (no wind data), generates asymmetric triangles
    at evenly-spaced bearings (full 360°) so that proximity-to-home and
    asymmetric-leg benefits still apply regardless of wind knowledge.

    Rotations spread around the upwind direction (or full circle if unknown).
    Leg ratios vary by safety profile.
    """
    routes = []
    ratios = _ASYM_RATIOS.get(safety_profile, _ASYM_RATIOS["standard"])

    if wind_dir is not None:
        # Wind-aware: cluster rotations around the upwind direction
        upwind_bearing = wind_dir
        spread = 120.0
        for ratio in ratios:
            leg1_frac = ratio[0]
            leg2_frac = ratio[1]
            for i in range(n_rotations):
                offset = -spread / 2 + (spread / max(1, n_rotations - 1)) * i
                base_bearing = (upwind_bearing + offset) % 360
                route = _build_asymmetric_triangle(
                    takeoff_lat, takeoff_lon, target_km,
                    base_bearing, leg1_frac, leg2_frac,
                )
                routes.append(route)
    else:
        # No wind: generate asymmetric triangles at full 360° rotation
        # so the proximity/asymmetry advantages still apply.
        n_full = max(n_rotations, 12)
        for ratio in ratios:
            leg1_frac = ratio[0]
            leg2_frac = ratio[1]
            for i in range(n_full):
                base_bearing = (360.0 / n_full) * i
                route = _build_asymmetric_triangle(
                    takeoff_lat, takeoff_lon, target_km,
                    base_bearing, leg1_frac, leg2_frac,
                )
                routes.append(route)
    return routes


def _build_asymmetric_triangle(
    takeoff_lat: float, takeoff_lon: float,
    target_km: float,
    base_bearing: float,
    leg1_frac: float, leg2_frac: float,
) -> list[tuple[float, float]]:
    """Build a single asymmetric triangle and rescale so total ≈ target_km."""
    raw_leg1_km = target_km * leg1_frac
    raw_leg2_km = target_km * leg2_frac

    tp1 = _destination(takeoff_lat, takeoff_lon, base_bearing, raw_leg1_km)
    tp2 = _destination(tp1[0], tp1[1], (base_bearing + 130) % 360, raw_leg2_km)

    # Measure actual total and rescale to hit target distance
    raw_total = (
        _haversine(takeoff_lat, takeoff_lon, tp1[0], tp1[1])
        + _haversine(tp1[0], tp1[1], tp2[0], tp2[1])
        + _haversine(tp2[0], tp2[1], takeoff_lat, takeoff_lon)
    )
    if raw_total > 0:
        scale = target_km / raw_total
    else:
        scale = 1.0
    scaled_leg1 = raw_leg1_km * scale
    scaled_leg2 = raw_leg2_km * scale

    tp1 = _destination(takeoff_lat, takeoff_lon, base_bearing, scaled_leg1)
    tp2 = _destination(tp1[0], tp1[1], (base_bearing + 130) % 360, scaled_leg2)

    return [
        (takeoff_lat, takeoff_lon),
        tp1,
        tp2,
        (takeoff_lat, takeoff_lon),
    ]


# ---------------------------------------------------------------------------
# Turnpoint → town name lookup (Overpass / OSM)
# ---------------------------------------------------------------------------

def _fetch_nearby_towns(
    points: list[tuple[float, float]],
    radius_km: float = 10.0,
) -> dict[tuple[float, float], dict]:
    """Query Overpass for towns/villages near the given points.

    Returns a mapping from (lat, lon) → {name, lat, lon, place_type, distance_km}
    for the closest settlement to each point.
    Only queries once with a bbox covering all points.
    """
    if not points:
        return {}

    # Build a bounding box covering all points + radius
    deg_margin = radius_km / 111.0  # rough km-to-degree conversion
    min_lat = min(p[0] for p in points) - deg_margin
    max_lat = max(p[0] for p in points) + deg_margin
    min_lon = min(p[1] for p in points) - deg_margin * 1.5  # lon degrees are narrower
    max_lon = max(p[1] for p in points) + deg_margin * 1.5

    bbox = f"{min_lat:.4f},{min_lon:.4f},{max_lat:.4f},{max_lon:.4f}"
    query = (
        f'[out:json][timeout:15];'
        f'(node["place"~"^(city|town|village)$"]({bbox}););'
        f'out body;'
    )

    try:
        resp = _requests.post(
            _OVERPASS_URL,
            data={"data": query},
            timeout=15,
            headers={"User-Agent": "SoaringCup/1.0 task-planner"},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        logger.warning("Overpass town lookup failed", exc_info=True)
        return {}

    # Parse OSM elements
    towns: list[dict] = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:en")
        if not name:
            continue
        towns.append({
            "name": name,
            "lat": el["lat"],
            "lon": el["lon"],
            "place_type": tags.get("place", ""),
        })

    if not towns:
        return {}

    # Prefer larger settlements — they are easier to spot from the air.
    # effective_distance = real_distance × weight  (lower = better)
    _place_weight = {"city": 0.25, "town": 0.50, "village": 1.0}

    result: dict[tuple[float, float], dict] = {}
    for pt in points:
        best = None
        best_eff = float("inf")
        for t in towns:
            d = _haversine(pt[0], pt[1], t["lat"], t["lon"])
            if d > radius_km:
                continue
            eff = d * _place_weight.get(t["place_type"], 1.0)
            if eff < best_eff:
                best_eff = eff
                best = {**t, "distance_km": round(d, 1)}
        if best:
            result[pt] = best

    logger.info("Town lookup: %d/%d turnpoints matched to towns (%d candidates)",
                len(result), len(points), len(towns))
    return result


def _label_route_with_towns(
    route: CandidateRoute,
    town_map: dict[tuple[float, float], dict],
    takeoff_name: str = "Takeoff",
) -> None:
    """Update leg from/to names and route description with town names."""
    for leg in route.legs:
        # Check 'from' point
        from_pt = (round(leg.from_lat, 4), round(leg.from_lon, 4))
        if from_pt in town_map:
            leg.from_name = town_map[from_pt]["name"]
        elif leg.from_name in ("Takeoff",):
            pass  # keep takeoff name
        # Check 'to' point
        to_pt = (round(leg.to_lat, 4), round(leg.to_lon, 4))
        if to_pt in town_map:
            leg.to_name = town_map[to_pt]["name"]
        elif leg.to_name in ("Finish",):
            pass  # keep finish name

    # Rebuild description with town names
    tp_names = []
    for leg in route.legs[:-1]:  # all legs except last (which ends at finish)
        tp_names.append(leg.to_name)

    is_oar = (len(route.turnpoints) == 3
              and route.turnpoints[0] == route.turnpoints[2])
    is_tri = (len(route.turnpoints) >= 4
              and route.turnpoints[0] == route.turnpoints[-1])

    if is_oar:
        route.description = (f"Out-and-return via {tp_names[0] if tp_names else '?'}, "
                             f"{route.total_distance_km:.0f}km")
    elif is_tri:
        route.description = (f"Triangle via {', '.join(tp_names)}, "
                             f"{route.total_distance_km:.0f}km")
    else:
        route.description = (f"Task via {', '.join(tp_names)}, "
                             f"{route.total_distance_km:.0f}km")


def optimize_task(
    takeoff_lat: float,
    takeoff_lon: float,
    target_km: float,
    weather_cells: list,
    *,
    dest_lat: Optional[float] = None,
    dest_lon: Optional[float] = None,
    soaring_mode: str = "thermal",
    safety_profile: str = "standard",
    airspace_result: Optional[dict] = None,
    airspace_checker=None,
    terrain_checker=None,
    top_n: int = 5,
    timed_cells: Optional[dict] = None,
    takeoff_hour: float = 11.0,
    max_duration_hours: float = 4.0,
    preferred_waypoints: Optional[list[tuple[float, float]]] = None,
) -> list[CandidateRoute]:
    """Generate and score candidate routes, return top N.

    Args:
        takeoff_lat, takeoff_lon: takeoff airport
        target_km: desired task distance
        weather_cells: list of WeatherCell objects from weather.py
        dest_lat, dest_lon: destination airport (None for same as takeoff)
        soaring_mode: 'thermal', 'ridge', 'wave'
        safety_profile: safety profile name
        airspace_result: pre-computed global airspace check (optional, legacy)
        airspace_checker: callable(points) -> airspace dict (optional, per-route)
        terrain_checker: callable(points) -> terrain result (optional)
        top_n: number of top candidates to return
        timed_cells: dict of time-windowed weather cells from weather.py
        takeoff_hour: estimated takeoff hour (local time)
        max_duration_hours: expected flight duration
        preferred_waypoints: list of (lat, lon) that the user wants in the route
    """
    raw_candidates = generate_candidates(
        takeoff_lat, takeoff_lon, target_km,
        dest_lat=dest_lat, dest_lon=dest_lon,
        soaring_mode=soaring_mode,
    )

    # Generate asymmetric triangle candidates — ALWAYS, not just when wind is known.
    # When wind is available, candidates cluster around the upwind direction.
    # When wind is missing, candidates cover all bearings so the proximity-to-home
    # and asymmetric-leg scoring advantages still differentiate them from equilateral.
    avg_wind_dir = _average_wind_direction(weather_cells)
    same_airport = (
        dest_lat is None or dest_lon is None
        or _haversine(takeoff_lat, takeoff_lon, dest_lat or 0, dest_lon or 0) < 5
    )
    if same_airport:
        wind_biased = _generate_wind_biased_triangles(
            takeoff_lat, takeoff_lon, target_km, avg_wind_dir,
            safety_profile=safety_profile, n_rotations=6,
        )
        raw_candidates.extend(wind_biased)
        logger.info("Added %d asymmetric triangle candidates (wind_dir=%s)",
                    len(wind_biased),
                    f"{avg_wind_dir:.0f}°" if avg_wind_dir is not None else "unknown")

    # Generate routes through user-preferred waypoints
    if preferred_waypoints:
        wp_routes = _generate_waypoint_routes(
            takeoff_lat, takeoff_lon, target_km, preferred_waypoints,
            dest_lat=dest_lat if not same_airport else None,
            dest_lon=dest_lon if not same_airport else None,
        )
        raw_candidates.extend(wp_routes)

    n_oar = sum(1 for c in raw_candidates if len(c) == 3 and c[0] == c[2])
    n_tri = sum(1 for c in raw_candidates if len(c) >= 4 and c[0] == c[-1])
    n_other = len(raw_candidates) - n_oar - n_tri
    logger.info(
        "Generated %d raw candidates: %d out-and-return, %d triangles, %d other (safety=%s)",
        len(raw_candidates), n_oar, n_tri, n_other, safety_profile,
    )

    # Max distance from home — safety constraint
    # Conservative: turnpoints stay within 60% of target distance from home
    # Standard: 75%, Aggressive: no limit
    max_dist_factor = {"conservative": 0.60, "standard": 0.75}.get(safety_profile)

    scored: list[CandidateRoute] = []
    skipped_distance = 0
    skipped_airspace = 0

    for points in raw_candidates:
        # Max-distance-from-home filter
        if max_dist_factor is not None:
            max_allowed = target_km * max_dist_factor
            max_dist = _max_distance_from_home(points, takeoff_lat, takeoff_lon)
            if max_dist > max_allowed:
                skipped_distance += 1
                logger.debug(
                    "Skipped route: max dist from home %.1fkm > limit %.1fkm",
                    max_dist, max_allowed,
                )
                continue

        # Per-candidate airspace check
        route_airspace = airspace_result  # fallback to global
        if airspace_checker:
            try:
                route_airspace = airspace_checker(points)
                if route_airspace is None:
                    # Airspace check failed — fail-closed: skip candidate
                    # rather than allowing a potentially unsafe route through.
                    skipped_airspace += 1
                    logger.debug("Skipped route: airspace check returned None (fail-closed)")
                    continue
                if route_airspace.get("has_blocking_conflict"):
                    skipped_airspace += 1
                    logger.debug(
                        "Skipped route: blocking airspace conflict (%s)",
                        [c.get("zone_name", "?") for c in route_airspace.get("conflicts", [])],
                    )
                    continue
            except Exception:
                # Exception during check — fail-closed: skip candidate
                skipped_airspace += 1
                logger.debug("Skipped route: airspace check raised (fail-closed)", exc_info=True)
                continue

        # Optional terrain check per candidate
        terrain_result = None
        if terrain_checker:
            try:
                terrain_result = terrain_checker(points)
            except Exception:
                logger.debug("Terrain check failed for candidate", exc_info=True)

        route = score_candidate(
            points, target_km, weather_cells,
            airspace_result=route_airspace,
            terrain_result=terrain_result,
            safety_profile=safety_profile,
            timed_cells=timed_cells,
            takeoff_hour=takeoff_hour,
            max_duration_hours=max_duration_hours,
        )
        scored.append(route)

    if skipped_distance or skipped_airspace:
        logger.info(
            "Filtered out %d routes (distance: %d, airspace: %d), %d remaining",
            skipped_distance + skipped_airspace, skipped_distance, skipped_airspace,
            len(scored),
        )

    # Sort by score descending
    scored.sort(key=lambda r: r.score, reverse=True)

    top = scored[:top_n]

    # Label top candidates with nearby town names (single Overpass lookup)
    all_turnpoints = set()
    for r in top:
        for pt in r.turnpoints[1:-1]:  # skip takeoff/finish
            all_turnpoints.add((round(pt[0], 4), round(pt[1], 4)))

    if all_turnpoints:
        town_map = _fetch_nearby_towns(list(all_turnpoints), radius_km=12.0)
        takeoff_label = "Takeoff"
        for r in top:
            _label_route_with_towns(r, town_map, takeoff_name=takeoff_label)

    for i, r in enumerate(top):
        logger.info("  #%d: %s (score=%.1f)", i + 1, r.description, r.score)
    return top


def estimate_flight_time(
    total_distance_km: float,
    glider_polar: Optional[dict] = None,
    avg_thermal_strength: Optional[float] = None,
    avg_wind_component: float = 0.0,
) -> dict:
    """Estimate flight duration and average speed.

    Uses simplified MacCready theory if glider polar is available.
    """
    # Default conservative estimates
    if not glider_polar:
        avg_speed_kmh = 80.0  # conservative club-class default
    else:
        # Best glide speed from polar (simplified)
        v2 = glider_polar.get("v2_kmh", 120)
        w2 = abs(glider_polar.get("w2_ms", 1.0))
        # MacCready speed adjustment for thermal strength
        mc = avg_thermal_strength or 1.5  # m/s assumed climb rate
        mc_speed = v2 * (1 + mc / (w2 * 3.6))  # rough approximation
        avg_speed_kmh = min(mc_speed, 150)  # cap at 150 km/h

    # Adjust for wind
    avg_speed_kmh += avg_wind_component * 1.852 * 0.3  # partial wind effect

    avg_speed_kmh = max(50, avg_speed_kmh)
    duration_hours = total_distance_km / avg_speed_kmh

    return {
        "estimated_duration_hours": round(duration_hours, 1),
        "estimated_speed_kmh": round(avg_speed_kmh, 0),
    }
