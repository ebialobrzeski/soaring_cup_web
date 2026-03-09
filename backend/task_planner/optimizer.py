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

logger = logging.getLogger(__name__)


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
                    "airspace_conflicts": leg.airspace_conflicts,
                }
                for leg in self.legs
            ],
        }


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Poland border geofence (simplified polygon — keeps routes inside Poland)
# This is a conservative approximation: points slightly inside the real border.
# Prevents routes from crossing into Belarus, Russia (Kaliningrad), Lithuania,
# Ukraine, Slovakia, Czech Republic, Germany, or over the Baltic Sea.
# ---------------------------------------------------------------------------

_POLAND_BORDER: list[tuple[float, float]] = [
    # (lat, lon) — clockwise from NW corner
    (54.83, 14.12),   # NW — Swinoujscie / Usedom
    (54.45, 16.20),   # N coast — Słupsk area
    (54.79, 18.40),   # N coast — Gdańsk Bay
    (54.38, 19.60),   # NE — Vistula Lagoon
    (54.35, 22.80),   # NE — near Suwałki
    (53.85, 23.55),   # E — north of Białystok (Poland/Belarus border)
    (52.70, 23.60),   # E — Biała Podlaska area
    (51.95, 23.65),   # E — Chełm area
    (51.25, 23.60),   # E — south of Lublin
    (50.85, 24.10),   # SE corner — near Hrubieszów
    (50.35, 23.50),   # SE — Zamość area
    (49.55, 22.70),   # S — Bieszczady
    (49.40, 22.15),   # S — Bieszczady west
    (49.30, 20.95),   # S — Tatry east
    (49.20, 20.05),   # S — Tatry center
    (49.45, 18.85),   # S — Żywiec
    (49.95, 18.30),   # S — Cieszyn
    (50.30, 16.30),   # SW — Kłodzko
    (50.35, 15.00),   # W — Jelenia Góra
    (51.05, 14.95),   # W — Zgorzelec
    (51.50, 14.70),   # W — south of Żary
    (51.80, 14.70),   # W — Gubin
    (52.35, 14.55),   # W — Słubice
    (52.75, 14.40),   # W — Kostrzyn
    (53.15, 14.25),   # NW — Szczecin area
    (53.85, 14.20),   # NW — north of Szczecin
    (54.83, 14.12),   # close polygon
]


def _point_in_polygon(lat: float, lon: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _route_inside_poland(points: list[tuple[float, float]]) -> bool:
    """Check that ALL route points are inside Poland border polygon."""
    for lat, lon in points:
        if not _point_in_polygon(lat, lon, _POLAND_BORDER):
            return False
    return True


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
    allow_border_crossing: bool = False,
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
        candidates.extend(_generate_out_and_return(takeoff_lat, takeoff_lon, target_km, 12))
        candidates.extend(_generate_triangles(takeoff_lat, takeoff_lon, target_km, 12))
        candidates.extend(_generate_fai_triangles(takeoff_lat, takeoff_lon, target_km, 8))
    else:
        # Sector routes between airports + some triangles from takeoff
        candidates.extend(
            _generate_sector_routes(takeoff_lat, takeoff_lon, dest_lat, dest_lon, target_km, 12)
        )
        candidates.extend(_generate_triangles(takeoff_lat, takeoff_lon, target_km, 8))

    # Hard filter: remove any route with waypoints outside Poland
    if not allow_border_crossing:
        before = len(candidates)
        candidates = [c for c in candidates if _route_inside_poland(c)]
        removed = before - len(candidates)
        if removed:
            logger.info("Geofence: removed %d/%d candidates outside Poland border", removed, before)
    else:
        logger.info("Geofence: DISABLED — border crossing allowed by user")

    return candidates


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


def score_candidate(
    points: list[tuple[float, float]],
    target_km: float,
    weather_cells: list,
    airspace_result: Optional[dict] = None,
    terrain_result: Optional[dict] = None,
    safety_profile: str = "standard",
) -> CandidateRoute:
    """Score a single candidate route.

    Returns a CandidateRoute with score 0-100.
    safety_profile affects route-type preference:
      - conservative/standard: multi-leg (triangle) routes get a bonus,
        out-and-return routes get a penalty.
      - aggressive: no route-type bias.
    """
    total_dist = _route_distance(points)

    # 1. Distance match (0-25 pts)
    dist_error = abs(total_dist - target_km) / target_km
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

    # 2. Thermal coverage (0-30 pts)
    thermal_score = 0.0
    thermal_legs = 0
    legs = []
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        dist = _haversine(p1[0], p1[1], p2[0], p2[1])
        brng = _bearing(p1[0], p1[1], p2[0], p2[1])

        # Sample midpoint weather
        mid_lat = (p1[0] + p2[0]) / 2
        mid_lon = (p1[1] + p2[1]) / 2
        cell = _nearest_cell(mid_lat, mid_lon, weather_cells)

        tq = None
        wind_comp = None
        if cell:
            # Thermal quality for this leg
            bl_ok = cell.bl_height is not None and cell.bl_height >= 1200
            ti_ok = cell.thermal_index is not None and cell.thermal_index >= 3.0
            if bl_ok and ti_ok:
                thermal_legs += 1
                tq = round(cell.thermal_index, 1)
            elif bl_ok or ti_ok:
                thermal_legs += 0.5
                tq = round((cell.thermal_index or 0), 1)

            # Wind component
            if cell.wind_speed_kts is not None and cell.wind_dir is not None:
                wc = calculate_wind_components(cell.wind_dir, cell.wind_speed_kts, brng)
                wind_comp = wc["headwind"]

        legs.append(TaskLeg(
            from_name=f"TP{i}" if i > 0 else "Takeoff",
            from_lat=p1[0], from_lon=p1[1],
            to_name=f"TP{i+1}" if i + 1 < len(points) - 1 else "Finish",
            to_lat=p2[0], to_lon=p2[1],
            distance_km=dist,
            bearing=brng,
            thermal_quality=tq,
            wind_component_kts=wind_comp,
        ))

    n_legs = len(legs) if legs else 1
    thermal_score = (thermal_legs / n_legs) * 30

    # 3. Wind exposure (0-20 pts) — minimize headwind on longest leg
    wind_score = 20.0
    longest_leg = max(legs, key=lambda l: l.distance_km) if legs else None
    if longest_leg and longest_leg.wind_component_kts is not None:
        hw = longest_leg.wind_component_kts
        if hw > 15:
            wind_score = 5.0
        elif hw > 10:
            wind_score = 10.0
        elif hw > 5:
            wind_score = 15.0
        # Tailwind bonus
        if hw < -5:
            wind_score = min(20, wind_score + 5)

    # 4. Terrain clearance (0-15 pts)
    terrain_score = 15.0  # default OK if no data
    if terrain_result:
        if not terrain_result.get("safe", True):
            terrain_score = 0.0
        elif terrain_result.get("max_terrain_m", 0) > 1500:
            terrain_score = 10.0  # mountainous but passable

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

    total_score = distance_score + thermal_score + wind_score + terrain_score + airspace_score

    # 6. Route-type preference based on safety profile (bonus/penalty)
    n_turnpoints = len(points) - 2  # exclude takeoff & finish
    is_out_and_return = (len(points) == 3 and points[0] == points[2])
    is_triangle = (len(points) >= 4 and points[0] == points[-1])

    route_type_bonus = 0.0
    if safety_profile in ("conservative", "standard"):
        if is_triangle:
            # Multi-leg routes keep the pilot within glide range of takeoff
            route_type_bonus = 15.0 if safety_profile == "conservative" else 10.0
            logger.debug("Triangle route +%.0f bonus (safety=%s)", route_type_bonus, safety_profile)
        elif is_out_and_return:
            # Out-and-return penalised: single leg far from base
            route_type_bonus = -10.0 if safety_profile == "conservative" else -5.0
            logger.debug("Out-and-return %.0f penalty (safety=%s)", route_type_bonus, safety_profile)
    total_score += route_type_bonus

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
        "(dist=%.0f therm=%.0f wind=%.0f terrain=%.0f airsp=%.0f type_bonus=%.0f)",
        route.description, total_dist, total_score,
        distance_score, thermal_score, wind_score, terrain_score, airspace_score, route_type_bonus,
    )

    return route


# ---------------------------------------------------------------------------
# Main optimizer
# ---------------------------------------------------------------------------

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
    allow_border_crossing: bool = False,
    top_n: int = 5,
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
    """
    raw_candidates = generate_candidates(
        takeoff_lat, takeoff_lon, target_km,
        dest_lat=dest_lat, dest_lon=dest_lon,
        soaring_mode=soaring_mode,
        allow_border_crossing=allow_border_crossing,
    )
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
                if route_airspace and route_airspace.get("has_blocking_conflict"):
                    skipped_airspace += 1
                    logger.debug(
                        "Skipped route: blocking airspace conflict (%s)",
                        [c.get("zone_name", "?") for c in route_airspace.get("conflicts", [])],
                    )
                    continue
            except Exception:
                logger.debug("Per-route airspace check failed", exc_info=True)

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
