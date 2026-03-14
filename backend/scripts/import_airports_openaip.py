"""Import global airport list from OpenAIP into the airports table.

Fetches airports country-by-country to stay within API pagination limits.
Safe to re-run — uses UPSERT so existing rows are updated in place.

Usage:
    python -m backend.scripts.import_airports_openaip
    python -m backend.scripts.import_airports_openaip --countries PL DE CZ SK
    python -m backend.scripts.import_airports_openaip --types 0 1 2 5
    python -m backend.scripts.import_airports_openaip --dry-run
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from pathlib import Path

import requests
import psycopg2
import psycopg2.extras

# Ensure project root is on sys.path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import DATABASE_URL, OPENAIP_API_KEY  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OPENAIP_BASE = "https://api.core.openaip.net/api"
PAGE_LIMIT = 300
REQUEST_DELAY_S = 0.3   # polite delay between API calls

# OpenAIP airport type IDs to import (all flyable sites)
# 0=AERODROME, 1=INTL_AERODROME, 2=AF_CIVIL, 3=AF_MIL_CIVIL,
# 4=AF_MIL, 5=GLIDER_SITE, 6=ULTRALIGHT_SITE
DEFAULT_TYPES = {0, 1, 2, 3, 4, 5, 6}

# ISO 3166-1 alpha-2 country codes — full global list
ALL_COUNTRIES: list[str] = [
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT",
    "AU", "AW", "AX", "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI",
    "BJ", "BL", "BM", "BN", "BO", "BQ", "BR", "BS", "BT", "BV", "BW", "BY",
    "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK", "CL", "CM", "CN",
    "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK",
    "FM", "FO", "FR", "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL",
    "GM", "GN", "GP", "GQ", "GR", "GS", "GT", "GU", "GW", "GY", "HK", "HM",
    "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN", "IO", "IQ", "IR",
    "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS",
    "LT", "LU", "LV", "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK",
    "ML", "MM", "MN", "MO", "MP", "MQ", "MR", "MS", "MT", "MU", "MV", "MW",
    "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI", "NL", "NO", "NP",
    "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW",
    "SA", "SB", "SC", "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM",
    "SN", "SO", "SR", "SS", "ST", "SV", "SX", "SY", "SZ", "TC", "TD", "TF",
    "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR", "TT", "TV", "TW",
    "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
]


def _headers() -> dict[str, str]:
    return {"x-openaip-api-key": OPENAIP_API_KEY, "Accept": "application/json"}


def _fetch_airports_for_country(country: str, allowed_types: set[int]) -> list[dict]:
    """Fetch all airports for a country code, all pages."""
    results: list[dict] = []
    page = 1
    while True:
        try:
            resp = requests.get(
                f"{OPENAIP_BASE}/airports",
                params={"country": country, "page": page, "limit": PAGE_LIMIT},
                headers=_headers(),
                timeout=30,
            )
            if resp.status_code == 404:
                break  # no airports for this country
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            logger.warning("OpenAIP error for %s page %d: %s", country, page, exc)
            break

        items = data.get("items", [])
        for item in items:
            if item.get("type", -1) in allowed_types:
                results.append(item)

        total = data.get("totalCount", len(items))
        if len(results) >= total or not items or page * PAGE_LIMIT >= total:
            break
        page += 1
        time.sleep(REQUEST_DELAY_S)

    return results


def _runway_direction(item: dict) -> str | None:
    """Extract primary runway heading from OpenAIP airport item."""
    runways = item.get("runways") or []
    if not runways:
        return None
    heading = runways[0].get("trueHeading")
    return str(int(heading)) if heading is not None else None


def _parse_airport(item: dict) -> dict:
    """Convert an OpenAIP airport item to our airports table row."""
    geo = item.get("geometry", {})
    coords = geo.get("coordinates", [0, 0])  # GeoJSON: [lon, lat]
    lon = float(coords[0]) if len(coords) > 0 else 0.0
    lat = float(coords[1]) if len(coords) > 1 else 0.0

    elevation = item.get("elevation")
    if isinstance(elevation, dict):
        elevation = elevation.get("value")
    elevation = int(elevation) if elevation is not None else None

    return {
        "id": str(item.get("_id", uuid.uuid4())),
        "icaoCode": item.get("icaoCode") or None,
        "name": item.get("name", "Unknown"),
        "latitude": lat,
        "longitude": lon,
        "elevation": elevation,
        "timezone": None,
        "country": item.get("country") or None,
        "isActive": True,
        "runwayDirection": _runway_direction(item),
    }


def run(
    countries: list[str] | None = None,
    allowed_types: set[int] | None = None,
    dry_run: bool = False,
) -> None:
    if not OPENAIP_API_KEY:
        logger.error("OPENAIP_API_KEY is not set — cannot fetch airports.")
        sys.exit(1)
    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set.")
        sys.exit(1)

    target_countries = countries or ALL_COUNTRIES
    target_types = allowed_types if allowed_types is not None else DEFAULT_TYPES

    logger.info(
        "Starting airport import: %d countries, types=%s, dry_run=%s",
        len(target_countries), sorted(target_types), dry_run,
    )

    db_url = DATABASE_URL.strip('"').strip("'")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    upsert_sql = """
        INSERT INTO airports (
            id, "icaoCode", name, latitude, longitude,
            elevation, timezone, country, "isActive", "runwayDirection",
            "createdAt", "updatedAt"
        ) VALUES (
            %(id)s, %(icaoCode)s, %(name)s, %(latitude)s, %(longitude)s,
            %(elevation)s, %(timezone)s, %(country)s, %(isActive)s, %(runwayDirection)s,
            NOW(), NOW()
        )
        ON CONFLICT (id) DO UPDATE SET
            "icaoCode"        = EXCLUDED."icaoCode",
            name              = EXCLUDED.name,
            latitude          = EXCLUDED.latitude,
            longitude         = EXCLUDED.longitude,
            elevation         = EXCLUDED.elevation,
            country           = EXCLUDED.country,
            "isActive"        = EXCLUDED."isActive",
            "runwayDirection" = EXCLUDED."runwayDirection",
            "updatedAt"       = NOW()
    """

    total_inserted = 0
    total_skipped = 0

    for i, country in enumerate(target_countries, 1):
        logger.info("[%d/%d] Fetching %s ...", i, len(target_countries), country)
        items = _fetch_airports_for_country(country, target_types)

        if not items:
            logger.debug("  %s: no airports", country)
            time.sleep(REQUEST_DELAY_S)
            continue

        rows = [_parse_airport(item) for item in items]

        if dry_run:
            logger.info("  %s: would upsert %d airports (dry run)", country, len(rows))
            total_inserted += len(rows)
        else:
            try:
                psycopg2.extras.execute_batch(cur, upsert_sql, rows, page_size=100)
                conn.commit()
                total_inserted += len(rows)
                logger.info("  %s: upserted %d airports", country, len(rows))
            except Exception:
                conn.rollback()
                logger.error("  %s: DB error — rolling back", country, exc_info=True)
                total_skipped += len(rows)

        time.sleep(REQUEST_DELAY_S)

    cur.close()
    conn.close()

    logger.info(
        "Import complete: %d airports upserted, %d skipped due to errors.",
        total_inserted, total_skipped,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import airports from OpenAIP into the airports table.")
    parser.add_argument(
        "--countries", nargs="+", metavar="CC",
        help="ISO 3166-1 alpha-2 country codes to import (default: all)",
    )
    parser.add_argument(
        "--types", nargs="+", type=int, metavar="N",
        help=f"OpenAIP airport type IDs to include (default: {sorted(DEFAULT_TYPES)}). "
             "0=AERODROME 1=INTL_AERODROME 2=AF_CIVIL 3=AF_MIL_CIVIL 4=AF_MIL "
             "5=GLIDER_SITE 6=ULTRALIGHT_SITE",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch data but do not write to DB")
    args = parser.parse_args()

    run(
        countries=args.countries,
        allowed_types=set(args.types) if args.types else None,
        dry_run=args.dry_run,
    )
