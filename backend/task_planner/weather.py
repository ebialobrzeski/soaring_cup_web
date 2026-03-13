"""Weather data fetching, mesh generation, cell summarization, and caching.

Sources (in priority order):
  1. Open-Meteo   — bulk grid forecast, free, no key needed
  2. Windy        — soaring-specific indices (thermal, BL, CAPE) for surviving cells
  3. IMGW-PIB     — high-res Polish actuals (supplement)

Strategy:
  1. Generate mesh grid points for the task area
  2. Check weather_cache for fresh data (< 2hr TTL)
  3. Fetch Open-Meteo bulk for all uncached points (general params + coarse BL)
  4. Apply precipitation/stability filter — discard bad cells
  5. For surviving cells only, call Windy for soaring-specific data
  6. Summarize each cell into a compact descriptor string for the LLM
"""
from __future__ import annotations

import json
import logging
import math
import time as _time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.config import IMGW_API_BASE_URL, WINDY_API_KEY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

# Time windows for weather bucketing (local solar time approximation)
TIME_WINDOWS = {
    "morning":   (9, 12),   # thermal development
    "midday":    (12, 15),  # peak thermals
    "afternoon": (15, 18),  # thermal decay
}


class WeatherCell:
    """A single grid-point forecast summary."""

    __slots__ = (
        "lat", "lon", "bl_height", "thermal_index", "cape", "cin",
        "cloud_base_ft", "cloud_cover", "wind_speed_kts", "wind_dir",
        "wind_gusts_kts", "temperature", "dew_point", "precipitation",
        "visibility", "solar_radiation", "lapse_rate", "pressure",
        "source", "raw", "time_window",
    )

    def __init__(self, **kwargs: Any):
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot))

    def to_dict(self) -> dict:
        return {s: getattr(self, s) for s in self.__slots__}

    def summary_line(self) -> str:
        """Compact one-line descriptor for the LLM."""
        tw = f"[{self.time_window}] " if self.time_window else ""
        parts = [f"{tw}{self.lat:.1f}N {self.lon:.1f}E:"]
        if self.bl_height is not None:
            parts.append(f"BL={self.bl_height}m")
        ti = self.thermal_index
        if ti is not None:
            label = "strong" if ti >= 7 else "moderate" if ti >= 4 else "weak"
            parts.append(f"thermal={label}({ti:.1f})")
        if self.wind_speed_kts is not None and self.wind_dir is not None:
            compass = _deg_to_compass(self.wind_dir)
            parts.append(f"wind={compass}{self.wind_speed_kts:.0f}kt")
        if self.cloud_base_ft is not None:
            parts.append(f"CB={self.cloud_base_ft}ft")
        if self.cape is not None:
            parts.append(f"CAPE={self.cape:.0f}")
        if self.precipitation is not None and self.precipitation > 0:
            parts.append(f"rain={self.precipitation:.1f}mm")
        else:
            parts.append("no rain")
        return " ".join(parts)


def _deg_to_compass(deg: int) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = round(deg / 45) % 8
    return dirs[idx]


# ---------------------------------------------------------------------------
# Mesh generation
# ---------------------------------------------------------------------------

def generate_mesh(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    *,
    dest_lat: Optional[float] = None,
    dest_lon: Optional[float] = None,
    spacing_km: float = 25.0,
) -> list[tuple[float, float]]:
    """Generate grid points for the task area.

    If dest_lat/dest_lon are provided and differ from center,
    creates a corridor mesh ±40km either side of the line.
    Otherwise creates a circular mesh.

    Returns list of (lat, lon) rounded to 2 decimal places.
    """
    points: set[tuple[float, float]] = set()

    if dest_lat is not None and dest_lon is not None:
        dist = _haversine(center_lat, center_lon, dest_lat, dest_lon)
        if dist > 5:  # different airports — corridor
            return _corridor_mesh(
                center_lat, center_lon, dest_lat, dest_lon,
                corridor_width_km=40, spacing_km=spacing_km,
            )

    # Circular mesh
    lat_step = spacing_km / 111.0  # ~111 km per degree latitude
    lon_step = spacing_km / (111.0 * math.cos(math.radians(center_lat)))

    lat_min = center_lat - radius_km / 111.0
    lat_max = center_lat + radius_km / 111.0
    lon_min = center_lon - radius_km / (111.0 * math.cos(math.radians(center_lat)))
    lon_max = center_lon + radius_km / (111.0 * math.cos(math.radians(center_lat)))

    lat = lat_min
    while lat <= lat_max:
        lon = lon_min
        while lon <= lon_max:
            if _haversine(center_lat, center_lon, lat, lon) <= radius_km:
                points.add((round(lat, 2), round(lon, 2)))
            lon += lon_step
        lat += lat_step

    return sorted(points)


def _corridor_mesh(
    lat1: float, lon1: float, lat2: float, lon2: float,
    corridor_width_km: float, spacing_km: float,
) -> list[tuple[float, float]]:
    """Generate mesh along a corridor between two points."""
    points: set[tuple[float, float]] = set()
    total_dist = _haversine(lat1, lon1, lat2, lon2)
    bearing = _bearing(lat1, lon1, lat2, lon2)
    perp_bearing = (bearing + 90) % 360

    n_along = max(2, int(total_dist / spacing_km) + 1)
    n_across = max(2, int(2 * corridor_width_km / spacing_km) + 1)

    for i in range(n_along + 1):
        frac = i / n_along
        mid_lat = lat1 + frac * (lat2 - lat1)
        mid_lon = lon1 + frac * (lon2 - lon1)
        for j in range(n_across + 1):
            offset = -corridor_width_km + j * (2 * corridor_width_km / n_across)
            pt = _destination(mid_lat, mid_lon, perp_bearing, offset)
            points.add((round(pt[0], 2), round(pt[1], 2)))

    return sorted(points)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in km between two points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees from point 1 to point 2."""
    dlon = math.radians(lon2 - lon1)
    lat1r, lat2r = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _destination(lat: float, lon: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Destination point from start + bearing + distance."""
    R = 6371.0
    d = dist_km / R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br))
    lon2 = lon1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
                              math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), math.degrees(lon2)


# ---------------------------------------------------------------------------
# Cache layer (weather_cache table)
# ---------------------------------------------------------------------------

def _get_cached_cells(
    db: Session,
    points: list[tuple[float, float]],
    forecast_date: date,
    source: str,
) -> dict[tuple[float, float], dict]:
    """Return cached weather data for grid points that are still fresh."""
    if not points:
        return {}
    cached: dict[tuple[float, float], dict] = {}
    now = datetime.now(timezone.utc)
    # Query in batches
    for i in range(0, len(points), 50):
        batch = points[i:i + 50]
        placeholders = ", ".join(f"({p[0]}, {p[1]})" for p in batch)
        rows = db.execute(
            text(f"""
                SELECT lat, lon, data FROM weather_cache
                WHERE (lat, lon) IN ({placeholders})
                  AND forecast_date = :fd AND source = :src
                  AND expires_at > :now
            """),
            {"fd": forecast_date, "src": source, "now": now},
        ).fetchall()
        for r in rows:
            cached[(float(r[0]), float(r[1]))] = r[2] if isinstance(r[2], dict) else json.loads(r[2])
    return cached


def _store_cached_cells(
    db: Session,
    cells: list[WeatherCell],
    forecast_date: date,
    model_run: str,
    source: str,
) -> None:
    """Store weather cells in cache with 2-hour TTL."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=2)
    for cell in cells:
        db.execute(
            text("""
                INSERT INTO weather_cache (lat, lon, forecast_date, model_run, source, data, fetched_at, expires_at)
                VALUES (:lat, :lon, :fd, :mr, :src, :data, :now, :exp)
                ON CONFLICT (lat, lon, forecast_date, model_run, source)
                DO UPDATE SET data = :data, fetched_at = :now, expires_at = :exp
            """),
            {
                "lat": round(cell.lat, 2), "lon": round(cell.lon, 2),
                "fd": forecast_date, "mr": model_run, "src": source,
                "data": json.dumps(cell.to_dict()), "now": now, "exp": expires,
            },
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Failed to cache weather cells", exc_info=True)


# ---------------------------------------------------------------------------
# Thermal estimation helpers (ported from openmeteo.ts)
# ---------------------------------------------------------------------------

def estimate_thermal_index_from_cape(
    cape: float,
    temperature: float,
    dew_point: float,
    cloud_cover_low: float,
) -> float:
    """Return thermal index 0–10."""
    if cape < 50:
        idx = 0.0
    elif cape < 200:
        idx = 0.5
    elif cape < 400:
        idx = 1.0
    elif cape < 700:
        idx = 2.0
    elif cape < 1000:
        idx = 3.0
    elif cape < 1500:
        idx = 4.0
    elif cape < 2000:
        idx = 4.5
    else:
        idx = 5.0

    # Temperature component (0–3)
    if temperature > 25:
        idx += 3
    elif temperature > 20:
        idx += 2
    elif temperature > 15:
        idx += 1

    # Temp-dew spread (0–2)
    spread = temperature - dew_point
    if spread > 12:
        idx += 2.0
    elif spread > 8:
        idx += 1.5
    elif spread > 5:
        idx += 1.0
    elif spread > 3:
        idx += 0.5

    # Penalties
    if cloud_cover_low > 80:
        idx -= 2
    elif cloud_cover_low > 60:
        idx -= 1
    if cape > 2500:
        idx -= 1  # overdevelopment risk

    return round(max(0.0, min(10.0, idx)), 1)


def estimate_cloud_base(
    freezing_level_m: float,
    temperature: float,
    dew_point: float,
) -> int:
    """Return cloud base estimate in feet AGL."""
    spread = temperature - dew_point
    convective_base_ft = int(spread * 400)
    freezing_level_ft = int(freezing_level_m * 3.28084)
    return max(200, min(convective_base_ft, freezing_level_ft))


def estimate_lapse_rate(
    temperature: float,
    dew_point: float,
    cloud_cover: float,
) -> float:
    """Estimate lapse rate (°C/1000ft) from surface observations."""
    lr = 2.0
    spread = temperature - dew_point
    if spread > 15:
        lr += 1.5
    elif spread > 10:
        lr += 1.0
    elif spread > 5:
        lr += 0.5
    if cloud_cover < 20:
        lr += 0.5
    elif cloud_cover > 70:
        lr -= 1.0
    return round(max(0.5, min(4.5, lr)), 2)


# ---------------------------------------------------------------------------
# Open-Meteo bulk fetch
# ---------------------------------------------------------------------------

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Parameters we need from Open-Meteo hourly endpoint
_OM_HOURLY_PARAMS = [
    "temperature_2m",
    "dew_point_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "cloud_cover",
    "cloud_cover_low",
    "precipitation",
    "visibility",
    "surface_pressure",
    "cape",
    "freezing_level_height",
    "shortwave_radiation",
    "boundary_layer_height",
]


def fetch_open_meteo(
    points: list[tuple[float, float]],
    forecast_date: date,
    start_hour: int = 6,
    end_hour: int = 21,
) -> tuple[list[WeatherCell], dict, dict[str, list[WeatherCell]]]:
    """Fetch general weather data from Open-Meteo for multiple grid points.

    Returns (cells, stats, timed_cells) where:
      cells      — averaged cells for the full soaring window (backward compat)
      stats      — call counts and timing
      timed_cells — dict keyed by time window name ('morning', 'midday', 'afternoon')
                    each mapping to a list of WeatherCell for that window
    """
    cells: list[WeatherCell] = []
    timed_cells: dict[str, list[WeatherCell]] = {tw: [] for tw in TIME_WINDOWS}
    date_str = forecast_date.isoformat()
    stats = {"calls": 0, "ok": 0, "errors": 0, "total_time_ms": 0}

    for lat, lon in points:
        t0 = _time.perf_counter()
        stats["calls"] += 1
        try:
            resp = requests.get(
                OPEN_METEO_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(_OM_HOURLY_PARAMS),
                    "start_date": date_str,
                    "end_date": date_str,
                    "timezone": "auto",
                },
                timeout=15,
            )
            resp.raise_for_status()
            elapsed = int((_time.perf_counter() - t0) * 1000)
            stats["total_time_ms"] += elapsed
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])

            # Full-window average (backward compatible)
            cell = _aggregate_open_meteo_hourly(lat, lon, hourly, times, start_hour, end_hour)
            if cell:
                cells.append(cell)
                stats["ok"] += 1

            # Time-bucketed cells from the same response
            for tw_name, (tw_start, tw_end) in TIME_WINDOWS.items():
                tw_cell = _aggregate_open_meteo_hourly(
                    lat, lon, hourly, times, tw_start, tw_end,
                    time_window=tw_name,
                )
                if tw_cell:
                    timed_cells[tw_name].append(tw_cell)

        except Exception:
            elapsed = int((_time.perf_counter() - t0) * 1000)
            stats["total_time_ms"] += elapsed
            stats["errors"] += 1
            logger.warning("Open-Meteo fetch failed for (%.2f, %.2f)", lat, lon, exc_info=True)

    logger.info("Open-Meteo: fetched %d/%d grid points (%dms), timed cells: %s",
                len(cells), len(points), stats["total_time_ms"],
                {tw: len(v) for tw, v in timed_cells.items()})
    return cells, stats, timed_cells


def _aggregate_open_meteo_hourly(
    lat: float,
    lon: float,
    hourly: dict,
    times: list[str],
    start_hour: int,
    end_hour: int,
    time_window: Optional[str] = None,
) -> Optional[WeatherCell]:
    """Average Open-Meteo hourly data over a time range.

    Args:
        time_window: optional label (e.g. 'morning', 'midday', 'afternoon')
                     stored on the returned cell for temporal scoring.
    """
    if not times:
        return None

    # Filter to soaring hours
    indices = []
    for i, t in enumerate(times):
        try:
            h = int(t.split("T")[1].split(":")[0])
            if start_hour <= h <= end_hour:
                indices.append(i)
        except (IndexError, ValueError):
            continue

    if not indices:
        return None

    def _avg(key: str) -> Optional[float]:
        vals = [hourly[key][i] for i in indices if hourly.get(key) and i < len(hourly[key]) and hourly[key][i] is not None]
        return sum(vals) / len(vals) if vals else None

    def _max_val(key: str) -> Optional[float]:
        vals = [hourly[key][i] for i in indices if hourly.get(key) and i < len(hourly[key]) and hourly[key][i] is not None]
        return max(vals) if vals else None

    temp = _avg("temperature_2m")
    dew = _avg("dew_point_2m")
    cape_val = _max_val("cape")
    cc = _avg("cloud_cover")
    cc_low = _avg("cloud_cover_low")
    bl = _max_val("boundary_layer_height")
    freezing = _avg("freezing_level_height")
    wind_ms = _avg("wind_speed_10m")
    wind_dir = _avg("wind_direction_10m")
    gusts_ms = _max_val("wind_gusts_10m")
    precip = _avg("precipitation")
    vis = _avg("visibility")
    pressure = _avg("surface_pressure")
    solar = _max_val("shortwave_radiation")

    # Derive soaring indices
    thermal_idx = None
    cloud_base = None
    lr = None
    if temp is not None and dew is not None:
        if cape_val is not None and cc_low is not None:
            thermal_idx = estimate_thermal_index_from_cape(cape_val, temp, dew, cc_low)
        if freezing is not None:
            cloud_base = estimate_cloud_base(freezing, temp, dew)
        if cc is not None:
            lr = estimate_lapse_rate(temp, dew, cc)

    wind_kts = wind_ms * 1.94384 if wind_ms is not None else None
    gust_kts = gusts_ms * 1.94384 if gusts_ms is not None else None

    return WeatherCell(
        lat=round(lat, 2),
        lon=round(lon, 2),
        bl_height=int(bl) if bl else None,
        thermal_index=thermal_idx,
        cape=cape_val,
        cin=None,  # Open-Meteo doesn't provide CIN directly
        cloud_base_ft=cloud_base,
        cloud_cover=int(cc) if cc is not None else None,
        wind_speed_kts=round(wind_kts, 1) if wind_kts is not None else None,
        wind_dir=int(wind_dir) if wind_dir is not None else None,
        wind_gusts_kts=round(gust_kts, 1) if gust_kts is not None else None,
        temperature=round(temp, 1) if temp is not None else None,
        dew_point=round(dew, 1) if dew is not None else None,
        precipitation=round(precip, 2) if precip is not None else None,
        visibility=int(vis) if vis is not None else None,
        solar_radiation=round(solar, 0) if solar is not None else None,
        lapse_rate=lr,
        pressure=round(pressure, 1) if pressure is not None else None,
        source="open-meteo",
        raw=None,
        time_window=time_window,
    )


# ---------------------------------------------------------------------------
# Coarse filter — discard cells with bad weather
# ---------------------------------------------------------------------------

def _seasonal_bl_min(forecast_date: date) -> int:
    """Return an adaptive BL-height threshold based on the month."""
    month = forecast_date.month
    if month in (6, 7, 8):          # summer
        return 800
    if month in (5, 9):             # shoulder season
        return 500
    if month in (4, 10):            # early spring / autumn
        return 350
    return 250                       # winter / early spring


def filter_cells(
    cells: list[WeatherCell],
    precip_threshold: float = 0.2,
    bl_min: int | None = None,
    forecast_date: date | None = None,
) -> tuple[list[WeatherCell], list[WeatherCell]]:
    """Split cells into (passing, failed) by coarse stability filter.

    If *bl_min* is not supplied it is derived from *forecast_date* using
    ``_seasonal_bl_min``.  When the filter discards **all** cells, the
    best cells by BL height are returned instead so the pipeline can
    still produce a marginal-conditions task.
    """
    if bl_min is None:
        bl_min = _seasonal_bl_min(forecast_date) if forecast_date else 800

    passing, failed = [], []
    for c in cells:
        if c.precipitation is not None and c.precipitation > precip_threshold:
            failed.append(c)
        elif c.bl_height is not None and c.bl_height < bl_min:
            failed.append(c)
        else:
            passing.append(c)

    # Fallback: if everything was filtered, return the best cells by BL so
    # the pipeline can still generate a marginal-conditions task.
    if not passing and cells:
        by_bl = sorted(cells, key=lambda c: c.bl_height or 0, reverse=True)
        # Keep the top third (at least 5 cells)
        n = max(5, len(by_bl) // 3)
        passing = by_bl[:n]
        failed = by_bl[n:]
        logger.warning(
            "All %d cells below BL threshold %dm — returning top %d by BL height (marginal conditions)",
            len(cells), bl_min, len(passing),
        )

    return passing, failed


# ---------------------------------------------------------------------------
# Windy soaring-specific indices (for surviving cells only)
# ---------------------------------------------------------------------------

WINDY_POINT_URL = "https://api.windy.com/api/point-forecast/v2"


def get_recommended_windy_model(latitude: float, longitude: float) -> str:
    """Select best Windy NWP model for the given coordinates."""
    if 30 <= latitude <= 72 and -25 <= longitude <= 45:
        return "iconEu"
    if 24 <= latitude <= 50 and -125 <= longitude <= -66:
        return "namConus"
    return "gfs"


def fetch_windy_soaring(
    points: list[tuple[float, float]],
    forecast_date: date,
) -> tuple[dict[tuple[float, float], dict], dict]:
    """Fetch soaring-specific data from Windy for given points.

    Returns (results_dict, stats) where stats tracks call counts/timing.
    """
    stats = {"calls": 0, "ok": 0, "errors": 0, "total_time_ms": 0}
    if not WINDY_API_KEY:
        logger.warning("WINDY_API_KEY not set — skipping Windy soaring data")
        return {}, stats

    results: dict[tuple[float, float], dict] = {}
    date_str = forecast_date.isoformat()

    for lat, lon in points:
        t0 = _time.perf_counter()
        stats["calls"] += 1
        try:
            model = get_recommended_windy_model(lat, lon)
            resp = requests.post(
                WINDY_POINT_URL,
                json={
                    "lat": lat,
                    "lon": lon,
                    "model": model,
                    "parameters": [
                        "wind", "temp", "dewpoint", "cape", "rh",
                        "lclouds", "mclouds", "hclouds",
                        "precip", "windGust"
                    ],
                    "levels": ["surface", "850h", "700h"],
                    "key": WINDY_API_KEY,
                },
                timeout=15,
            )
            if not resp.ok:
                logger.warning("Windy API %d for (%.2f, %.2f): %s",
                               resp.status_code, lat, lon, resp.text[:300])
            resp.raise_for_status()
            elapsed = int((_time.perf_counter() - t0) * 1000)
            stats["total_time_ms"] += elapsed
            stats["ok"] += 1
            data = resp.json()

            # Extract soaring data — Windy returns arrays indexed by time
            ts_list = data.get("ts", [])
            target_ts = int(datetime.combine(forecast_date, datetime.min.time().replace(hour=12),
                                              tzinfo=timezone.utc).timestamp() * 1000)

            # Find closest timestamp to noon
            best_idx = 0
            if ts_list:
                best_idx = min(range(len(ts_list)), key=lambda i: abs(ts_list[i] - target_ts))

            cape_arr = data.get("cape-surface", [])
            rh_arr = data.get("rh-surface", [])
            lclouds_arr = data.get("lclouds-surface", [])
            mclouds_arr = data.get("mclouds-surface", [])
            hclouds_arr = data.get("hclouds-surface", [])
            precip_arr = data.get("past3hprecip-surface", [])
            gust_arr = data.get("gust-surface", [])

            # Extract values at best_idx
            cape = float(cape_arr[best_idx]) if cape_arr and best_idx < len(cape_arr) else None
            rh = float(rh_arr[best_idx]) if rh_arr and best_idx < len(rh_arr) else None
            lclouds = float(lclouds_arr[best_idx]) if lclouds_arr and best_idx < len(lclouds_arr) else 0
            mclouds = float(mclouds_arr[best_idx]) if mclouds_arr and best_idx < len(mclouds_arr) else 0
            hclouds = float(hclouds_arr[best_idx]) if hclouds_arr and best_idx < len(hclouds_arr) else 0
            precip = float(precip_arr[best_idx]) if precip_arr and best_idx < len(precip_arr) else 0
            gust_ms = float(gust_arr[best_idx]) if gust_arr and best_idx < len(gust_arr) else None

            # Compute total cloud cover (weighted average - low clouds matter most)
            cloud_cover = None
            if any(c is not None for c in [lclouds, mclouds, hclouds]):
                cloud_cover = (lclouds * 0.5 + mclouds * 0.3 + hclouds * 0.2)

            results[(round(lat, 2), round(lon, 2))] = {
                "bl_height": None,  # not available from Windy; Open-Meteo provides this
                "cape": cape,
                "rh": rh,
                "cloud_cover": cloud_cover,
                "precipitation": precip,
                "wind_gusts_kts": gust_ms * 1.94384 if gust_ms is not None else None,  # m/s to knots
            }

        except Exception:
            elapsed = int((_time.perf_counter() - t0) * 1000)
            stats["total_time_ms"] += elapsed
            stats["errors"] += 1
            logger.warning("Windy fetch failed for (%.2f, %.2f)", lat, lon, exc_info=True)

    logger.info("Windy: fetched soaring data for %d/%d points (%dms)", len(results), len(points), stats["total_time_ms"])
    return results, stats


def enrich_cells_with_windy(
    cells: list[WeatherCell],
    windy_data: dict[tuple[float, float], dict],
) -> None:
    """Merge Windy soaring data into existing weather cells (in-place)."""
    for cell in cells:
        key = (round(cell.lat, 2), round(cell.lon, 2))
        wd = windy_data.get(key)
        if not wd:
            continue
        
        # Merge all available Windy data
        if wd.get("bl_height") is not None:
            cell.bl_height = wd["bl_height"]
        
        # Cloud cover from Windy is often more accurate
        if wd.get("cloud_cover") is not None:
            cell.cloud_cover = wd["cloud_cover"]
        
        # Precipitation data
        if wd.get("precipitation") is not None:
            cell.precipitation = wd["precipitation"]
        
        # Wind gusts for safety assessment
        if wd.get("wind_gusts_kts") is not None:
            cell.wind_gusts_kts = wd["wind_gusts_kts"]
        
        # CAPE and thermal index recalculation
        if wd.get("cape") is not None:
            cell.cape = wd["cape"]
            # Recalculate thermal index with refined CAPE and cloud cover
            if cell.temperature is not None and cell.dew_point is not None:
                cell.thermal_index = estimate_thermal_index_from_cape(
                    cell.cape, cell.temperature, cell.dew_point,
                    cell.cloud_cover or 50,
                )
        
        # Log if RH indicates conditions worth noting
        rh = wd.get("rh")
        if rh is not None:
            if rh < 30:
                logger.debug("Cell (%.2f, %.2f): Low RH %.0f%% - blue thermals likely",
                            cell.lat, cell.lon, rh)
            elif rh > 80:
                logger.debug("Cell (%.2f, %.2f): High RH %.0f%% - overdevelopment risk",
                            cell.lat, cell.lon, rh)


# ---------------------------------------------------------------------------
# IMGW-PIB supplement (Polish tasks)
# ---------------------------------------------------------------------------

IMGW_STATIONS: dict[str, tuple[float, float]] = {
    # Major Polish met stations with coordinates for Haversine matching
    "Warszawa": (52.17, 20.97),
    "Kraków": (50.08, 19.80),
    "Wrocław": (51.10, 16.88),
    "Poznań": (52.42, 16.83),
    "Gdańsk": (54.38, 18.60),
    "Katowice": (50.24, 19.02),
    "Łódź": (51.72, 19.40),
    "Lublin": (51.22, 22.40),
    "Białystok": (53.10, 23.16),
    "Rzeszów": (50.11, 22.02),
    "Jelenia Góra": (50.90, 15.73),
    "Leszno": (51.84, 16.58),
    "Kielce": (50.81, 20.70),
    "Zakopane": (49.30, 19.95),
    "Nowy Targ": (49.48, 20.03),
}


def _is_in_poland(lat: float, lon: float) -> bool:
    """Rough check if coordinates are within Poland's bounding box."""
    return 49.0 <= lat <= 54.9 and 14.1 <= lon <= 24.2


def fetch_imgw_supplement(
    center_lat: float,
    center_lon: float,
) -> tuple[Optional[dict], dict]:
    """Fetch current synoptic data from nearest IMGW station.

    Returns (data_dict_or_None, stats).
    """
    stats = {"calls": 0, "ok": 0, "errors": 0, "total_time_ms": 0}
    if not _is_in_poland(center_lat, center_lon):
        return None, stats

    t0 = _time.perf_counter()
    stats["calls"] = 1
    try:
        resp = requests.get(f"{IMGW_API_BASE_URL}/synop", timeout=10)
        resp.raise_for_status()
        stations = resp.json()
    except Exception:
        elapsed = int((_time.perf_counter() - t0) * 1000)
        stats["total_time_ms"] = elapsed
        stats["errors"] = 1
        logger.warning("IMGW synop fetch failed", exc_info=True)
        return None, stats

    # Find nearest station
    best_dist = float("inf")
    best_data = None
    for s in stations:
        name = s.get("stacja", "")
        coords = IMGW_STATIONS.get(name)
        if not coords:
            continue
        dist = _haversine(center_lat, center_lon, coords[0], coords[1])
        if dist < best_dist:
            best_dist = dist
            best_data = s

    if not best_data or best_dist > 100:  # skip if > 100km away
        return None

    try:
        wind_ms = float(best_data.get("predkosc_wiatru", 0))
        wind_dir_raw = best_data.get("kierunek_wiatru", "")
        temp = float(best_data.get("temperatura", 0))
        humidity = float(best_data.get("wilgotnosc_wzgledna", 50))
        vis_km = float(best_data.get("widzialnosc", 10))

        # Parse wind direction (may be numeric or compass text)
        try:
            wind_dir = int(wind_dir_raw)
        except (ValueError, TypeError):
            compass_map = {"N": 0, "NE": 45, "E": 90, "SE": 135, "S": 180, "SW": 225, "W": 270, "NW": 315}
            wind_dir = compass_map.get(str(wind_dir_raw).upper(), 0)

        # Estimate dew point from Magnus formula
        import math as _m
        alpha = (17.27 * temp) / (237.7 + temp) + _m.log(humidity / 100)
        dew = 237.7 * alpha / (17.27 - alpha)

        return {
            "station": best_data.get("stacja"),
            "distance_km": round(best_dist, 1),
            "wind_speed_kts": round(wind_ms * 1.94384, 1),
            "wind_direction": wind_dir,
            "temperature": temp,
            "dew_point": round(dew, 1),
            "humidity": int(humidity),
            "visibility_m": int(vis_km * 1000),
            "attribution": "Źródłem pochodzenia danych jest IMGW-PIB",
        }, _finalize_imgw_stats(stats, t0, ok=True)
    except Exception:
        logger.warning("Failed to parse IMGW station data", exc_info=True)
        return None, _finalize_imgw_stats(stats, t0, ok=False)


def _finalize_imgw_stats(stats: dict, t0: float, *, ok: bool) -> dict:
    stats["total_time_ms"] = int((_time.perf_counter() - t0) * 1000)
    if ok:
        stats["ok"] = 1
    else:
        stats["errors"] = 1
    return stats


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def fetch_weather_grid(
    db: Session,
    takeoff_lat: float,
    takeoff_lon: float,
    target_distance_km: float,
    forecast_date: date,
    *,
    dest_lat: Optional[float] = None,
    dest_lon: Optional[float] = None,
    start_hour: int = 6,
    end_hour: int = 21,
) -> tuple[list[WeatherCell], dict]:
    """Full weather fetch pipeline for the task area.

    Returns (cells, metadata) where metadata includes IMGW supplement, etc.
    """
    # 1. Generate mesh
    radius_km = target_distance_km * 0.6 + 20  # task area radius with buffer
    mesh = generate_mesh(
        takeoff_lat, takeoff_lon, radius_km,
        dest_lat=dest_lat, dest_lon=dest_lon,
    )
    logger.info("Weather mesh: %d grid points (radius %.0fkm)", len(mesh), radius_km)

    # 2. Check cache
    model_run = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00Z")
    try:
        cached = _get_cached_cells(db, mesh, forecast_date, "open-meteo")
    except Exception:
        cached = {}
        logger.warning("Cache read failed", exc_info=True)

    uncached = [p for p in mesh if p not in cached]
    logger.info("Cache: %d hits, %d to fetch", len(cached), len(uncached))

    # 3. Open-Meteo bulk fetch for uncached
    fresh_cells, om_stats, timed_cells = fetch_open_meteo(uncached, forecast_date, start_hour, end_hour)

    # Store fresh cells in cache
    if fresh_cells:
        try:
            _store_cached_cells(db, fresh_cells, forecast_date, model_run, "open-meteo")
        except Exception:
            logger.warning("Cache store failed", exc_info=True)

    # Combine cached + fresh
    all_cells: list[WeatherCell] = []
    for p, data in cached.items():
        all_cells.append(WeatherCell(**data))
    all_cells.extend(fresh_cells)

    # Also add cached cells into timed buckets (they have no time_window, use as midday proxy)
    for p, data in cached.items():
        for tw_name in TIME_WINDOWS:
            c = WeatherCell(**data)
            c.time_window = tw_name
            timed_cells.setdefault(tw_name, []).append(c)

    # 4. Coarse filter
    passing, failed = filter_cells(all_cells, forecast_date=forecast_date)
    logger.info("Filter: %d passing, %d discarded (BL threshold %dm for %s)",
                len(passing), len(failed),
                _seasonal_bl_min(forecast_date), forecast_date)

    # 5. Windy enrichment for surviving cells
    windy_stats = {"calls": 0, "ok": 0, "errors": 0, "total_time_ms": 0}
    if passing and WINDY_API_KEY:
        surviving_points = [(c.lat, c.lon) for c in passing]
        # Limit Windy calls to max 20 points to conserve quota
        if len(surviving_points) > 20:
            # Sample evenly
            step = len(surviving_points) // 20
            surviving_points = surviving_points[::step][:20]
        windy_data, windy_stats = fetch_windy_soaring(surviving_points, forecast_date)
        enrich_cells_with_windy(passing, windy_data)
        # Also enrich timed cells with Windy data
        for tw_name in TIME_WINDOWS:
            enrich_cells_with_windy(timed_cells.get(tw_name, []), windy_data)

    # 6. IMGW supplement for Polish tasks
    imgw, imgw_stats = fetch_imgw_supplement(takeoff_lat, takeoff_lon)

    metadata = {
        "mesh_points": len(mesh),
        "cached": len(cached),
        "fetched": len(fresh_cells),
        "passing": len(passing),
        "failed": len(failed),
        "imgw_station": imgw,
        "timed_cells": timed_cells,
        "api_stats": {
            "open_meteo": om_stats,
            "windy": windy_stats,
            "imgw": imgw_stats,
        },
    }

    return passing, metadata
