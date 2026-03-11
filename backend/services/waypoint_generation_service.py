"""Waypoint Generation Service.

Provides two data sources:
1. OpenAIP API — airports, obstacles, navaids, hotspots, hang-gliding sites
   fetched on-demand by bounding box.  Requires OPENAIP_API_KEY in env/config.
2. OpenStreetMap populated places fetched on-demand via the Overpass API.
   Covers cities, towns, and villages annotated as CUP-style waypoints.

Public API
----------
query_openaip_aviation(min_lat, max_lat, min_lon, max_lon, types) -> list[Waypoint]
query_osm_places(min_lat, max_lat, min_lon, max_lon, types) -> list[Waypoint]
generate_waypoints(db, min_lat, max_lat, min_lon, max_lon, types) -> dict
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Sequence

import requests
from sqlalchemy.orm import Session

from backend.models.legacy import Waypoint
from backend import config
from backend.task_planner.terrain import get_elevations

logger = logging.getLogger(__name__)

# OSM Overpass endpoint (public)
_OVERPASS_URL = 'https://overpass-api.de/api/interpreter'

# OpenAIP API base
_OPENAIP_BASE = 'https://api.core.openaip.net/api'

# Maximum allowed bbox area (degrees²) to prevent huge queries
_MAX_BBOX_AREA_DEG2 = 36.0  # ~6°×6° ≈ 660km×660km at mid-latitudes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_coordinate(coord_str: str) -> float:
    """Parse CUP DDmm.mmmD coordinate to decimal degrees."""
    coord_str = coord_str.strip()
    match = re.match(r'(\d{2,3})(\d{2})\.(\d{3})([NSEW])', coord_str)
    if not match:
        return 0.0
    degrees = int(match.group(1))
    minutes = int(match.group(2))
    decimals = int(match.group(3))
    direction = match.group(4)
    decimal_degrees = degrees + (minutes + decimals / 1000.0) / 60.0
    if direction in ('S', 'W'):
        decimal_degrees = -decimal_degrees
    return decimal_degrees


def _parse_numeric(value: str) -> int:
    """Strip units and return int (e.g. '1350.0m' → 1350)."""
    if not value:
        return 0
    stripped = re.sub(r'[^\d.-]', '', str(value))
    try:
        return int(float(stripped)) if stripped else 0
    except (ValueError, AttributeError):
        return 0


def _make_code(name: str) -> str:
    """Generate a short 6-char uppercase code from a place name."""
    # Remove diacritics
    normalized = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(c for c in normalized if not unicodedata.combining(c))
    # Keep only alphanumeric
    alnum = re.sub(r'[^A-Za-z0-9]', '', ascii_name).upper()
    return alnum[:6] if alnum else name[:6].upper()


# ---------------------------------------------------------------------------
# OpenAIP aviation query (live API)
# ---------------------------------------------------------------------------

# OpenAIP airport type IDs → our category mapping
# https://docs.openaip.net/#tag/Airports/operation/GetAirports
_OPENAIP_AIRPORT_TYPES = {
    0: 'airports',   # AERODROME
    1: 'airports',   # INTL_AERODROME
    2: 'airports',   # AF_CIVIL
    3: 'airports',   # AF_MIL_CIVIL
    4: 'airports',   # AF_MIL
    5: 'outlandings', # GLIDER_SITE
    6: 'outlandings', # ULTRALIGHT_SITE
    7: 'outlandings', # HELIPORT_CIVIL
    8: 'outlandings', # HELIPORT_MIL
    9: 'outlandings', # HELIPORT_HOSPITAL
    14: 'outlandings', # HANG_GLIDING
    15: 'outlandings', # PARA_GLIDING
}

# CUP style codes to assign to OpenAIP results
_OPENAIP_AIRPORT_CUP_STYLE = {
    'airports': 5,      # fallback: airfield with hard runway
    'outlandings': 3,   # outlanding
}

# OpenAIP runway surface mainComposite values that indicate a paved/hard surface
# 0=ASPH (asphalt), 1=CONC (concrete) — everything else is soft/grass/unknown
_HARD_SURFACE_COMPOSITES: frozenset[int] = frozenset({0, 1})


def _airport_cup_style(item: dict, category: str) -> int:
    """Return the appropriate CUP style for an OpenAIP airport item.

    - outlandings (incl. heliports, ultralight sites) → 3
    - GLIDER_SITE (OpenAIP type 5) → 4  (glider airfield)
    - airports with any paved/hard runway → 5
    - airports with only soft/grass runways → 2
    """
    apt_type = item.get('type', -1)

    if category == 'outlandings':
        # Glider sites have a proper runway — more accurately a glider airfield
        return 4 if apt_type == 5 else 3

    # category == 'airports': check runway surfaces
    runways = item.get('runways', [])
    for rwy in runways:
        surface = rwy.get('surface') or {}
        if isinstance(surface, dict):
            composite = surface.get('mainComposite')
            if composite in _HARD_SURFACE_COMPOSITES:
                return 5  # paved runway found
    # No paved runway — treat as grass/soft airfield
    return 2

# OpenAIP obstacle → CUP style 8 (Transmitter mast); closest generic obstacle in CUP spec
_OPENAIP_OBSTACLE_CUP_STYLE = 8

# OpenAIP navaid type IDs → CUP style
# https://docs.openaip.net/#tag/Navaids
_OPENAIP_NAVAID_CUP_STYLE: dict[int, int] = {
    2: 10,  # NDB → CUP NDB
    3: 9,   # VOR → CUP VOR
    4: 9,   # DME → CUP VOR (closest)
    5: 9,   # ILS — treat as VOR
    7: 9,   # TACAN
    8: 9,   # VORTAC
}
_OPENAIP_NAVAID_DEFAULT_CUP_STYLE = 9


def _openaip_headers() -> dict:
    key = config.OPENAIP_API_KEY
    if not key:
        raise RuntimeError('OPENAIP_API_KEY is not set in configuration.')
    return {'x-openaip-api-key': key, 'Accept': 'application/json'}


def _openaip_bbox_param(min_lat: float, max_lat: float, min_lon: float, max_lon: float) -> str:
    """Return bbox as GeoJSON Polygon WKT for OpenAIP geometry filter."""
    # OpenAIP accepts: geometry=min_lon,min_lat,max_lon,max_lat  (W,S,E,N)
    return f'{min_lon},{min_lat},{max_lon},{max_lat}'


def _fetch_openaip_pages(endpoint: str, params: dict, headers: dict) -> list[dict]:
    """Fetch all pages from an OpenAIP paginated endpoint."""
    results = []
    page = 1
    while True:
        params['page'] = page
        params['limit'] = 300
        try:
            resp = requests.get(
                f'{_OPENAIP_BASE}/{endpoint}',
                params=params,
                headers=headers,
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(f'OpenAIP API error ({endpoint}): {exc}') from exc
        except ValueError as exc:
            raise RuntimeError(f'OpenAIP returned invalid JSON ({endpoint})') from exc

        items = data.get('items', [])
        results.extend(items)

        total = data.get('totalCount', len(items))
        if len(results) >= total or not items:
            break
        page += 1

    return results


def query_openaip_aviation(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    types: Sequence[str],
) -> list[Waypoint]:
    """Fetch aviation waypoints from OpenAIP for the given bbox.

    types is a subset of ['airports', 'outlandings', 'obstacles', 'hotspots', 'navaids', 'hang_glidings'].
    """
    headers = _openaip_headers()
    bbox = _openaip_bbox_param(min_lat, max_lat, min_lon, max_lon)
    waypoints: list[Waypoint] = []

    want_airports = 'airports' in types
    want_outlandings = 'outlandings' in types
    want_obstacles = 'obstacles' in types
    want_hotspots = 'hotspots' in types
    want_navaids = 'navaids' in types
    want_hang_glidings = 'hang_glidings' in types

    # ── Airports / airfields / glider sites ──────────────────────────────────
    if want_airports or want_outlandings:
        try:
            items = _fetch_openaip_pages('airports', {'bbox': bbox}, headers)
        except RuntimeError:
            raise

        for item in items:
            apt_type = item.get('type', -1)
            category = _OPENAIP_AIRPORT_TYPES.get(apt_type)
            if category == 'airports' and not want_airports:
                continue
            if category == 'outlandings' and not want_outlandings:
                continue
            if category is None:
                continue

            name = item.get('name', '') or ''
            if not name:
                continue

            geo = item.get('geometry', {})
            coords = geo.get('coordinates', [0, 0])
            lon, lat = float(coords[0]), float(coords[1])

            icao = item.get('icaoCode', '') or item.get('iataCode', '') or ''
            code = icao.strip() or _make_code(name)

            country = item.get('country', '') or ''
            elev_obj = item.get('elevation', {})
            elev = int(elev_obj.get('value', 0) or 0) if elev_obj else 0

            freq = ''
            frequencies = item.get('frequencies', [])
            if frequencies:
                primary = next((f for f in frequencies if f.get('primary')), frequencies[0])
                freq = str(primary.get('value', '')) or ''

            cup_style = _airport_cup_style(item, category)

            waypoints.append(Waypoint(
                name=name,
                code=code,
                country=country,
                latitude=lat,
                longitude=lon,
                elevation=elev,
                style=cup_style,
                frequency=freq,
                description=item.get('icaoCode', '') or '',
            ))

    # ── Obstacles ─────────────────────────────────────────────────────────────
    if want_obstacles:
        try:
            items = _fetch_openaip_pages('obstacles', {'bbox': bbox}, headers)
        except RuntimeError:
            raise

        for item in items:
            name = item.get('name', '') or ''
            if not name:
                # Build a name from type + height if no name given
                obs_type = item.get('type', '')
                height = item.get('height', {})
                val = height.get('value', '') if isinstance(height, dict) else ''
                name = f'{obs_type} {val}m'.strip() if val else obs_type or 'Obstacle'

            geo = item.get('geometry', {})
            coords = geo.get('coordinates', [0, 0])
            lon, lat = float(coords[0]), float(coords[1])

            elev_obj = item.get('elevation', {})
            elev = int(elev_obj.get('value', 0) or 0) if isinstance(elev_obj, dict) else 0

            waypoints.append(Waypoint(
                name=name,
                code=_make_code(name),
                country=item.get('country', '') or '',
                latitude=lat,
                longitude=lon,
                elevation=elev,
                style=_OPENAIP_OBSTACLE_CUP_STYLE,
                description='Obstacle',
            ))

    # ── Navaids (VOR, NDB, DME …) ─────────────────────────────────────────────
    if want_navaids:
        try:
            items = _fetch_openaip_pages('navaids', {'bbox': bbox}, headers)
        except RuntimeError:
            raise

        for item in items:
            name = item.get('name', '') or item.get('icaoCode', '') or ''
            if not name:
                continue

            geo = item.get('geometry', {})
            coords = geo.get('coordinates', [0, 0])
            lon, lat = float(coords[0]), float(coords[1])

            nav_type = item.get('type', -1)
            cup_style = _OPENAIP_NAVAID_CUP_STYLE.get(nav_type, _OPENAIP_NAVAID_DEFAULT_CUP_STYLE)

            elev_obj = item.get('elevation', {})
            elev = int(elev_obj.get('value', 0) or 0) if isinstance(elev_obj, dict) else 0

            freq = ''
            freq_val = item.get('frequency', {})
            if isinstance(freq_val, dict):
                freq = str(freq_val.get('value', '')) or ''

            icao = item.get('icaoCode', '') or ''
            code = icao.strip() or _make_code(name)

            waypoints.append(Waypoint(
                name=name,
                code=code,
                country=item.get('country', '') or '',
                latitude=lat,
                longitude=lon,
                elevation=elev,
                style=cup_style,
                frequency=freq,
                description=item.get('icaoCode', '') or '',
            ))

    # ── Thermal hotspots ──────────────────────────────────────────────────────
    if want_hotspots:
        try:
            items = _fetch_openaip_pages('hotspots', {'bbox': bbox}, headers)
        except RuntimeError:
            raise

        for item in items:
            name = item.get('name', '') or ''
            if not name:
                continue

            geo = item.get('geometry', {})
            coords = geo.get('coordinates', [0, 0])
            lon, lat = float(coords[0]), float(coords[1])

            elev_obj = item.get('elevation', {})
            elev = int(elev_obj.get('value', 0) or 0) if isinstance(elev_obj, dict) else 0

            waypoints.append(Waypoint(
                name=name,
                code=_make_code(name),
                country=item.get('country', '') or '',
                latitude=lat,
                longitude=lon,
                elevation=elev,
                style=20,  # CUP: Thermal
                description='Thermal hotspot',
            ))

    # ── Hang gliding / paragliding sites ─────────────────────────────────────
    if want_hang_glidings:
        try:
            items = _fetch_openaip_pages('hang-glidings', {'bbox': bbox}, headers)
        except RuntimeError:
            raise

        for item in items:
            name = item.get('name', '') or ''
            if not name:
                continue

            geo = item.get('geometry', {})
            coords = geo.get('coordinates', [0, 0])
            lon, lat = float(coords[0]), float(coords[1])

            elev_obj = item.get('elevation', {})
            elev = int(elev_obj.get('value', 0) or 0) if isinstance(elev_obj, dict) else 0

            waypoints.append(Waypoint(
                name=name,
                code=_make_code(name),
                country=item.get('country', '') or '',
                latitude=lat,
                longitude=lon,
                elevation=elev,
                style=3,  # CUP: Outlanding (closest to a launch/landing site)
                description='Hang gliding / paragliding site',
            ))

    return waypoints





# ---------------------------------------------------------------------------
# OSM Overpass query — populated places
# ---------------------------------------------------------------------------

_OSM_PLACE_TYPES = {
    'cities': ('city',),
    'towns': ('city', 'town'),
    'villages': ('city', 'town', 'village'),
}

# CUP style for populated places
_PLACE_STYLE = 1  # generic waypoint


def query_osm_places(
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    types: Sequence[str],
) -> list[Waypoint]:
    """Query Overpass API for populated places within a bounding box.

    `types` is a subset of ['cities', 'towns', 'villages'].
    Each level is inclusive (villages includes city + town + village).
    """
    # Collect the most inclusive place type set requested
    place_set: set[str] = set()
    for t in types:
        if t in _OSM_PLACE_TYPES:
            place_set |= set(_OSM_PLACE_TYPES[t])

    if not place_set:
        return []

    place_regex = '|'.join(sorted(place_set))
    bbox = f'{min_lat},{min_lon},{max_lat},{max_lon}'
    query = (
        f'[out:json][timeout:25];'
        f'(node["place"~"^({place_regex})$"]({bbox}););'
        f'out body;'
        f'>>;'
        f'is_in;'
        f'area._["boundary"="administrative"]["admin_level"="2"];'
        f'out tags;'
    )

    try:
        resp = requests.post(
            _OVERPASS_URL,
            data={'data': query},
            timeout=30,
            headers={'User-Agent': 'GlidePlan/1.0 waypoint-generator'},
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning('Overpass API request failed: %s', exc)
        raise RuntimeError(f'OpenStreetMap query failed: {exc}') from exc
    except ValueError as exc:
        logger.warning('Overpass API returned invalid JSON: %s', exc)
        raise RuntimeError('OpenStreetMap returned invalid data.') from exc

    waypoints: list[Waypoint] = []
    for element in data.get('elements', []):
        tags = element.get('tags', {})
        name = tags.get('name') or tags.get('name:en') or ''
        if not name:
            continue
        place_type = tags.get('place', '')

        # Filter by what was actually requested (not just the regex union)
        keep = False
        if 'cities' in types and place_type == 'city':
            keep = True
        if 'towns' in types and place_type in ('city', 'town'):
            keep = True
        if 'villages' in types and place_type in ('city', 'town', 'village'):
            keep = True
        if not keep:
            continue

        lat = element.get('lat', 0.0)
        lon = element.get('lon', 0.0)
        population = tags.get('population', '')
        country = tags.get('addr:country') or tags.get('is_in:country_code', '')
        ele_raw = tags.get('ele', '')
        try:
            elev = int(float(ele_raw)) if ele_raw else None
        except (ValueError, TypeError):
            elev = None

        desc_parts = [place_type.capitalize()]
        if population:
            try:
                desc_parts.append(f'pop. {int(population):,}')
            except ValueError:
                pass
        description = ' / '.join(desc_parts)

        waypoints.append(Waypoint(
            name=name,
            code=_make_code(name),
            country=country,
            latitude=float(lat),
            longitude=float(lon),
            elevation=elev if elev is not None else 0,
            style=_PLACE_STYLE,
            description=description,
        ))

    # Batch-fetch elevation for any waypoint that had no OSM ele tag
    missing = [(wp.latitude, wp.longitude) for wp in waypoints if wp.elevation == 0]
    if missing:
        try:
            elev_map = get_elevations(missing)
            for wp in waypoints:
                if wp.elevation == 0:
                    wp.elevation = elev_map.get((wp.latitude, wp.longitude), 0)
        except Exception:
            logger.warning('Batch elevation fetch failed for OSM places; elevations will be 0.')

    return waypoints


# ---------------------------------------------------------------------------
# Combined entry point
# ---------------------------------------------------------------------------

def generate_waypoints(
    db: Session,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    types: Sequence[str],
) -> dict:
    """Generate waypoints for the given bbox and type list.

    Returns::
        {
            'waypoints': [Waypoint, ...],
            'sources': {'aviation': int, 'osm': int},
            'warnings': [str, ...],
        }
    """
    warnings: list[str] = []

    # Guard against huge bboxes
    area = (max_lat - min_lat) * (max_lon - min_lon)
    if area > _MAX_BBOX_AREA_DEG2:
        warnings.append(
            'Selected area is very large – results have been limited to aviation waypoints only. '
            'Please select a smaller area for populated places.'
        )

    aviation_types = [t for t in types if t in ('airports', 'outlandings', 'obstacles', 'hotspots', 'navaids', 'hang_glidings')]
    osm_types = [t for t in types if t in ('cities', 'towns', 'villages')]

    # If area is too large, suppress OSM queries
    if area > _MAX_BBOX_AREA_DEG2:
        osm_types = []

    aviation_wps: list[Waypoint] = []
    aviation_error: str | None = None
    if aviation_types:
        try:
            aviation_wps = query_openaip_aviation(min_lat, max_lat, min_lon, max_lon, aviation_types)
        except RuntimeError as exc:
            aviation_error = str(exc)
            warnings.append(f'Aviation waypoints could not be fetched: {aviation_error}')

    osm_wps: list[Waypoint] = []
    osm_error: str | None = None
    if osm_types:
        try:
            osm_wps = query_osm_places(min_lat, max_lat, min_lon, max_lon, osm_types)
        except RuntimeError as exc:
            osm_error = str(exc)
            warnings.append(f'Populated places could not be fetched: {osm_error}')

    result: dict = {
        'waypoints': aviation_wps + osm_wps,
        'sources': {'aviation': len(aviation_wps), 'osm': len(osm_wps)},
        'warnings': warnings,
    }
    if aviation_error:
        result['aviation_error'] = aviation_error
    if osm_error:
        result['osm_error'] = osm_error
    return result
