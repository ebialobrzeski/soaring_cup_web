"""Glider polar importer — fetches polar data from XCSoar PolarStore.cpp and inserts into DB.

Usage:
    python -m backend.task_planner.glider_import          # import all gliders
    python -m backend.task_planner.glider_import --dry     # preview only
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.config import DATABASE_URL  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

XCSOAR_POLAR_URL = (
    "https://raw.githubusercontent.com/XCSoar/XCSoar/master/src/Polar/PolarStore.cpp"
)

# Regex to match one polar entry line:
#   { "Name", max_gross, ballast, v1, w1, v2, w2, v3, w3, wing_area, ref_mass, handicap, empty_mass }
_ENTRY_RE = re.compile(
    r'\{\s*"([^"]+)"\s*,'     # name
    r'\s*([\d.]+)\s*,'        # max_gross_kg
    r'\s*([\d.]+)\s*,'        # max_ballast_l
    r'\s*([\d.]+)\s*,'        # v1_kmh
    r'\s*([-\d.]+)\s*,'       # w1_ms
    r'\s*([\d.]+)\s*,'        # v2_kmh
    r'\s*([-\d.]+)\s*,'       # w2_ms
    r'\s*([\d.]+)\s*,'        # v3_kmh
    r'\s*([-\d.]+)\s*,'       # w3_ms
    r'\s*([\d.]+)\s*,'        # wing_area_m2
    r'\s*([\d.]+)\s*,'        # reference_mass_kg
    r'\s*(\d+)\s*,'           # handicap
    r'\s*(\d+)\s*'            # empty_mass_kg
    r'\}'
)


def _compute_polar_coefficients(
    v1: float, w1: float, v2: float, w2: float, v3: float, w3: float
) -> tuple[float, float, float]:
    """Compute polar polynomial w = a*v² + b*v + c by least-squares fit.

    Speeds are converted from km/h to m/s for SI units.
    Returns (a, b, c).
    """
    speeds_ms = np.array([v1, v2, v3]) / 3.6  # km/h -> m/s
    sinks = np.array([w1, w2, w3])

    # Build Vandermonde matrix for quadratic fit: [v², v, 1]
    A = np.column_stack([speeds_ms**2, speeds_ms, np.ones_like(speeds_ms)])
    coeffs, *_ = np.linalg.lstsq(A, sinks, rcond=None)
    return float(coeffs[0]), float(coeffs[1]), float(coeffs[2])


def fetch_polar_data() -> list[dict]:
    """Fetch and parse XCSoar PolarStore.cpp into a list of glider dicts."""
    logger.info("Fetching PolarStore.cpp from XCSoar repository...")
    resp = requests.get(XCSOAR_POLAR_URL, timeout=30)
    resp.raise_for_status()
    text = resp.text

    # Also grab the default polar (LS-8)
    entries = []
    for m in _ENTRY_RE.finditer(text):
        name = m.group(1)
        v1 = float(m.group(4))
        w1 = float(m.group(5))
        v2 = float(m.group(6))
        w2 = float(m.group(7))
        v3 = float(m.group(8))
        w3 = float(m.group(9))
        wing_area = float(m.group(10))
        ref_mass = float(m.group(11))

        a, b, c = _compute_polar_coefficients(v1, w1, v2, w2, v3, w3)

        entries.append({
            "name": name,
            "source": "xcsoar",
            "max_gross_kg": int(float(m.group(2))),
            "max_ballast_l": int(float(m.group(3))),
            "v1_kmh": v1,
            "w1_ms": w1,
            "v2_kmh": v2,
            "w2_ms": w2,
            "v3_kmh": v3,
            "w3_ms": w3,
            "wing_area_m2": wing_area if wing_area > 0 else None,
            "reference_mass_kg": ref_mass if ref_mass > 0 else None,
            "handicap": int(m.group(12)) or None,
            "empty_mass_kg": int(m.group(13)) or None,
            "polar_a": a,
            "polar_b": b,
            "polar_c": c,
        })

    logger.info("Parsed %d glider polars from XCSoar.", len(entries))
    return entries


def import_gliders(dry_run: bool = False) -> int:
    """Import glider polars into the database. Returns count of inserted rows."""
    entries = fetch_polar_data()
    if not entries:
        logger.warning("No polar entries found — nothing to import.")
        return 0

    if dry_run:
        for e in entries:
            logger.info("  [DRY] %s  (%s kg, handicap %s)", e["name"], e["max_gross_kg"], e["handicap"])
        logger.info("DRY RUN — %d gliders would be imported.", len(entries))
        return len(entries)

    import psycopg2  # type: ignore

    conn = psycopg2.connect(DATABASE_URL.strip('"').strip("'"))
    conn.autocommit = False
    cur = conn.cursor()

    inserted = 0
    try:
        for e in entries:
            cur.execute(
                """
                INSERT INTO glider_polars (
                    name, source, max_gross_kg, max_ballast_l,
                    v1_kmh, w1_ms, v2_kmh, w2_ms, v3_kmh, w3_ms,
                    wing_area_m2, reference_mass_kg, handicap, empty_mass_kg,
                    polar_a, polar_b, polar_c
                ) VALUES (
                    %(name)s, %(source)s, %(max_gross_kg)s, %(max_ballast_l)s,
                    %(v1_kmh)s, %(w1_ms)s, %(v2_kmh)s, %(w2_ms)s, %(v3_kmh)s, %(w3_ms)s,
                    %(wing_area_m2)s, %(reference_mass_kg)s, %(handicap)s, %(empty_mass_kg)s,
                    %(polar_a)s, %(polar_b)s, %(polar_c)s
                )
                ON CONFLICT (name) DO UPDATE SET
                    source = EXCLUDED.source,
                    max_gross_kg = EXCLUDED.max_gross_kg,
                    max_ballast_l = EXCLUDED.max_ballast_l,
                    v1_kmh = EXCLUDED.v1_kmh, w1_ms = EXCLUDED.w1_ms,
                    v2_kmh = EXCLUDED.v2_kmh, w2_ms = EXCLUDED.w2_ms,
                    v3_kmh = EXCLUDED.v3_kmh, w3_ms = EXCLUDED.w3_ms,
                    wing_area_m2 = EXCLUDED.wing_area_m2,
                    reference_mass_kg = EXCLUDED.reference_mass_kg,
                    handicap = EXCLUDED.handicap,
                    empty_mass_kg = EXCLUDED.empty_mass_kg,
                    polar_a = EXCLUDED.polar_a,
                    polar_b = EXCLUDED.polar_b,
                    polar_c = EXCLUDED.polar_c
                """,
                e,
            )
            inserted += 1

        conn.commit()
        logger.info("Imported %d glider polars into the database.", inserted)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

    return inserted


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import glider polars from XCSoar.")
    parser.add_argument("--dry", action="store_true", help="Preview only, no DB changes.")
    args = parser.parse_args()
    import_gliders(dry_run=args.dry)
