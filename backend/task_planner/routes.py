"""AI Task Planner blueprint — /api/planner/* endpoints.

Routes:
  GET  /api/airspace/openaip           — fetch OpenAIP airspace zones for map bounds (public)
  POST /api/planner/generate           — generate an AI task proposal (premium)
  GET  /api/planner/gliders            — list available glider polars (premium)
  POST /api/planner/gliders            — create a custom user glider (login)
  GET  /api/planner/gliders/<id>/polar — get full polar data for chart (premium)
  PATCH /api/planner/gliders/<id>      — update a custom user glider (login)
  DELETE /api/planner/gliders/<id>     — delete a custom user glider (login)
  GET  /api/planner/airports           — search airports by name/ICAO (premium)
  POST /api/planner/airspace           — check airspace conflicts for given points (premium)
  GET  /api/planner/sessions           — list user's planner sessions (premium)
  GET  /api/planner/sessions/<id>      — load a single session (premium)
  DELETE /api/planner/sessions/<id>    — delete a session (premium)
  PATCH /api/planner/sessions/<id>     — rename a session (premium)
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime

from flask import Blueprint, g, jsonify, request
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.services.usage_service import log_request as _log_request
from backend.task_planner.ai_service import generate_task_routes, validate_ai_route
from backend.task_planner.airspace import (
    check_task_airspace,
    compute_airspace_score,
    fetch_airspace_from_openaip,
)
from backend.task_planner.optimizer import (
    estimate_flight_time,
    geocode_place,
)
from backend.task_planner.waypoints import discover_waypoints
from backend.task_planner.terrain import check_task_terrain
from backend.task_planner.weather import fetch_weather_grid
from backend.utils.auth_decorators import login_required

logger = logging.getLogger(__name__)

ai_planner_bp = Blueprint("ai_planner", __name__)


@ai_planner_bp.before_request
def _start_timer():
    g._aip_start = time.perf_counter()


@ai_planner_bp.after_request
def _track_usage(response):
    start = getattr(g, "_aip_start", None)
    if start is None:
        return response
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    external_calls = getattr(g, "_aip_external_calls", None)
    try:
        db = get_db()
        _log_request(
            db,
            response_status=response.status_code,
            response_time_ms=elapsed_ms,
            external_calls=external_calls,
        )
    except Exception:
        logger.debug("Usage logging failed (non-critical)", exc_info=True)
    return response


# ── OpenAIP airspace for Task Planner map ────────────────────────────────────

# Map OpenAIP zone types to the OpenAir class codes the frontend renderer uses
_TYPE_TO_OPENAIR_CLS = {
    "RESTRICTED": "R",
    "PROHIBITED": "P",
    "DANGER": "D",
    "CTR": "CTR",
    "TMA": "C",
    "FIR": "FIR",
    "UIR": "FIR",
    "RMZ": "RMZ",
    "TMZ": "TMZ",
    "ATZ": "CTR",
    "GLIDER_SECTOR": "W",
    "AERIAL_SPORTING": "W",
}


@ai_planner_bp.route("/api/airspace/openaip", methods=["GET"])
def openaip_airspace():
    """Fetch OpenAIP airspace polygons for the given map bounding box.

    Query params:
        south, west, north, east — map bounds (required)
    Returns:
        JSON list of airspace objects matching the frontend renderer format.
    """
    try:
        south = float(request.args["south"])
        west = float(request.args["west"])
        north = float(request.args["north"])
        east = float(request.args["east"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "south, west, north, east params required (floats)."}), 400

    # Clamp to reasonable bounds to avoid huge fetches
    if abs(north - south) > 10 or abs(east - west) > 15:
        return jsonify({"error": "Area too large — zoom in (max ~10° lat × 15° lon)."}), 400

    bbox = (south, west, north, east)
    zones = fetch_airspace_from_openaip(bbox)

    # Convert to the format the frontend task-planner.js renderer expects
    result = []
    for z in zones:
        cls = _TYPE_TO_OPENAIR_CLS.get(z.type, z.airspace_class)
        result.append({
            "cls": cls,
            "name": z.name,
            "altLower": z.lower_limit_ft,
            "altUpper": z.upper_limit_ft,
            "points": [[lat, lon] for lat, lon in z.polygon],
            "circles": [],
            "type": z.type,
            "country": z.country,
            "requires_transponder": z.requires_transponder,
            "requires_flight_plan": z.requires_flight_plan,
        })

    return jsonify(result)


# ── Glider list ──────────────────────────────────────────────────────────────

@ai_planner_bp.route("/api/planner/gliders", methods=["GET"])
@login_required
def list_gliders():
    """Return available glider polars for the dropdown.
    
    Returns global gliders plus the current user's custom gliders.
    """
    db = get_db()
    user_id = str(current_user.id) if current_user.is_authenticated else None
    try:
        rows = db.execute(
            text("""
                SELECT id, name, max_gross_kg, max_ballast_l, wing_area_m2, user_id, v1_kmh, v3_kmh
                FROM glider_polars
                WHERE user_id IS NULL OR user_id = :uid
                ORDER BY user_id NULLS LAST, name
            """),
            {"uid": user_id},
        ).fetchall()
        gliders = [
            {
                "id": str(r[0]),
                "name": r[1],
                "max_gross_kg": r[2],
                "max_ballast_l": r[3],
                "wing_area_m2": r[4],
                "is_custom": r[5] is not None,
                "v1_kmh": float(r[6]) if r[6] is not None else None,
                "v3_kmh": float(r[7]) if r[7] is not None else None,
            }
            for r in rows
        ]
    except Exception:
        gliders = []
    return jsonify(gliders)


@ai_planner_bp.route("/api/planner/gliders/<glider_id>/polar", methods=["GET"])
@login_required
def get_glider_polar(glider_id: str):
    """Return full polar data for a glider (for chart rendering)."""
    db = get_db()
    user_id = str(current_user.id)
    try:
        row = db.execute(
            text("""
                SELECT id, name, polar_a, polar_b, polar_c,
                       v1_kmh, w1_ms, v2_kmh, w2_ms, v3_kmh, w3_ms,
                       max_gross_kg, reference_mass_kg, wing_area_m2, handicap, user_id
                FROM glider_polars
                WHERE id = :gid AND (user_id IS NULL OR user_id = :uid)
            """),
            {"gid": glider_id, "uid": user_id},
        ).fetchone()
    except Exception:
        return jsonify({"error": "Database error"}), 500

    if not row:
        return jsonify({"error": "Glider not found"}), 404

    return jsonify({
        "id": str(row[0]),
        "name": row[1],
        "polar_a": row[2],
        "polar_b": row[3],
        "polar_c": row[4],
        "v1_kmh": row[5], "w1_ms": row[6],
        "v2_kmh": row[7], "w2_ms": row[8],
        "v3_kmh": row[9], "w3_ms": row[10],
        "max_gross_kg": row[11],
        "reference_mass_kg": row[12],
        "wing_area_m2": row[13],
        "handicap": row[14],
        "is_custom": row[15] is not None,
    })


@ai_planner_bp.route("/api/planner/gliders", methods=["POST"])
@login_required
def create_glider():
    """Create a custom user glider polar."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Glider name is required."}), 400

    try:
        v1 = float(data["v1_kmh"])
        w1 = float(data["w1_ms"])
        v2 = float(data["v2_kmh"])
        w2 = float(data["w2_ms"])
        v3 = float(data["v3_kmh"])
        w3 = float(data["w3_ms"])
        max_gross = int(data.get("max_gross_kg") or 500)
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid polar data: {exc}"}), 400

    # Compute polar coefficients via least-squares fit
    import numpy as np
    speeds_ms = np.array([v1, v2, v3]) / 3.6
    sinks = np.array([w1, w2, w3])
    A = np.column_stack([speeds_ms**2, speeds_ms, np.ones_like(speeds_ms)])
    coeffs, *_ = np.linalg.lstsq(A, sinks, rcond=None)
    polar_a, polar_b, polar_c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])

    db = get_db()
    user_id = str(current_user.id)
    try:
        row = db.execute(
            text("""
                INSERT INTO glider_polars
                    (name, source, user_id, max_gross_kg, max_ballast_l,
                     v1_kmh, w1_ms, v2_kmh, w2_ms, v3_kmh, w3_ms,
                     polar_a, polar_b, polar_c)
                VALUES
                    (:name, 'custom', :uid, :max_gross, 0,
                     :v1, :w1, :v2, :w2, :v3, :w3,
                     :pa, :pb, :pc)
                RETURNING id
            """),
            {
                "name": name, "uid": user_id, "max_gross": max_gross,
                "v1": v1, "w1": w1, "v2": v2, "w2": w2, "v3": v3, "w3": w3,
                "pa": polar_a, "pb": polar_b, "pc": polar_c,
            },
        ).fetchone()
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Create glider error")
        return jsonify({"error": "Could not save glider."}), 500

    return jsonify({"id": str(row[0]), "name": name, "is_custom": True}), 201


@ai_planner_bp.route("/api/planner/gliders/<glider_id>", methods=["PATCH"])
@login_required
def update_glider(glider_id: str):
    """Update a custom glider (user must own it)."""
    db = get_db()
    user_id = str(current_user.id)

    # Verify ownership
    existing = db.execute(
        text("SELECT id FROM glider_polars WHERE id = :gid AND user_id = :uid"),
        {"gid": glider_id, "uid": user_id},
    ).fetchone()
    if not existing:
        return jsonify({"error": "Glider not found or not yours."}), 404

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Glider name is required."}), 400

    try:
        v1 = float(data["v1_kmh"])
        w1 = float(data["w1_ms"])
        v2 = float(data["v2_kmh"])
        w2 = float(data["w2_ms"])
        v3 = float(data["v3_kmh"])
        w3 = float(data["w3_ms"])
        max_gross = int(data.get("max_gross_kg") or 500)
    except (KeyError, ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid polar data: {exc}"}), 400

    import numpy as np
    speeds_ms = np.array([v1, v2, v3]) / 3.6
    sinks = np.array([w1, w2, w3])
    A = np.column_stack([speeds_ms**2, speeds_ms, np.ones_like(speeds_ms)])
    coeffs, *_ = np.linalg.lstsq(A, sinks, rcond=None)
    polar_a, polar_b, polar_c = float(coeffs[0]), float(coeffs[1]), float(coeffs[2])

    try:
        db.execute(
            text("""
                UPDATE glider_polars SET
                    name = :name, max_gross_kg = :max_gross,
                    v1_kmh = :v1, w1_ms = :w1, v2_kmh = :v2, w2_ms = :w2,
                    v3_kmh = :v3, w3_ms = :w3,
                    polar_a = :pa, polar_b = :pb, polar_c = :pc
                WHERE id = :gid AND user_id = :uid
            """),
            {
                "name": name, "max_gross": max_gross,
                "v1": v1, "w1": w1, "v2": v2, "w2": w2, "v3": v3, "w3": w3,
                "pa": polar_a, "pb": polar_b, "pc": polar_c,
                "gid": glider_id, "uid": user_id,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Update glider error")
        return jsonify({"error": "Could not update glider."}), 500

    return jsonify({"ok": True})


@ai_planner_bp.route("/api/planner/gliders/<glider_id>", methods=["DELETE"])
@login_required
def delete_glider(glider_id: str):
    """Delete a custom glider (user must own it)."""
    db = get_db()
    user_id = str(current_user.id)
    result = db.execute(
        text("DELETE FROM glider_polars WHERE id = :gid AND user_id = :uid"),
        {"gid": glider_id, "uid": user_id},
    )
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Glider not found or not yours."}), 404
    return jsonify({"ok": True})


# ── Airport search ───────────────────────────────────────────────────────────

@ai_planner_bp.route("/api/planner/airports", methods=["GET"])
@login_required
def search_airports():
    """Search airports by name or ICAO code.

    Query params:
        q — search term (min 2 chars)
    Returns:
        JSON list of matching airports (max 20).
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])

    db = get_db()
    pattern = f"%{q}%"
    rows = db.execute(
        text("""
            SELECT id, "icaoCode", name, latitude, longitude, elevation, country
            FROM airports
            WHERE "isActive" = true
              AND (name ILIKE :pat OR "icaoCode" ILIKE :pat)
            ORDER BY
                CASE WHEN "icaoCode" ILIKE :pat THEN 0 ELSE 1 END,
                name
            LIMIT 20
        """),
        {"pat": pattern},
    ).fetchall()

    return jsonify([
        {
            "id": str(r[0]),
            "icao": r[1] or "",
            "name": r[2],
            "lat": r[3],
            "lon": r[4],
            "elevation": r[5],
            "country": r[6],
        }
        for r in rows
    ])


# ── Airspace check ───────────────────────────────────────────────────────────

@ai_planner_bp.route("/api/planner/airspace", methods=["POST"])
@login_required
def check_airspace():
    """Check airspace conflicts for a set of task points."""
    data = request.get_json(silent=True) or {}
    points_raw = data.get("points", [])
    flight_date_str = data.get("flight_date")
    safety_profile = data.get("safety_profile", "standard")
    constraints = data.get("constraints")

    if not points_raw or len(points_raw) < 2:
        return jsonify({"error": "At least 2 task points required."}), 400

    try:
        points = [(float(p["lat"]), float(p["lon"])) for p in points_raw]
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "Points must have numeric lat/lon."}), 400

    if flight_date_str:
        try:
            flight_date = date.fromisoformat(flight_date_str)
        except ValueError:
            return jsonify({"error": "Invalid flight_date format (YYYY-MM-DD)."}), 400
    else:
        flight_date = date.today()

    db = get_db()
    result = check_task_airspace(db, points, flight_date, safety_profile, constraints)
    score = compute_airspace_score(result)

    return jsonify({
        "score": score,
        "has_blocking_conflict": result.has_blocking_conflict,
        "conflicts": [
            {
                "zone_name": c.zone_name,
                "zone_type": c.zone_type,
                "airspace_class": c.airspace_class,
                "leg_index": c.leg_index,
                "requires_transponder": c.requires_transponder,
                "requires_flight_plan": c.requires_flight_plan,
                "is_notam": c.is_notam,
                "notam_id": c.notam_id,
                "suggestion": c.suggestion,
            }
            for c in result.conflicts
        ],
        "zones_count": len(result.zones_in_area),
        "notams_count": len(result.notams_in_area),
    })


# ── Generate task proposal ───────────────────────────────────────────────────

@ai_planner_bp.route("/api/planner/generate", methods=["POST"])
@login_required
def generate_task():
    """Generate an AI task proposal based on user inputs.

    Expects JSON body with:
      - takeoff_airport: str (ICAO code or name)
      - destination_airport: str (ICAO code or name, may equal takeoff)
      - target_distance_km: float
      - flight_date: str (YYYY-MM-DD)
      - max_duration_hours: float
      - takeoff_time: str (HH:MM, optional)
      - glider_id: str (UUID, optional)
      - safety_profile: 'conservative' | 'standard' | 'aggressive'
      - soaring_mode: 'thermal' | 'ridge' | 'wave'
      - constraints: dict (airspace toggles)
    """
    data = request.get_json(silent=True) or {}

    # Resolve user's OpenRouter API key (BYOK)
    user_api_key = ""
    if current_user.openrouter_key_enc:
        try:
            from backend.utils.crypto import decrypt_value
            user_api_key = decrypt_value(current_user.openrouter_key_enc)
        except Exception:
            logger.warning("Failed to decrypt user API key for user %s", current_user.id)

    # Validate required fields
    required = ["takeoff_airport", "target_distance_km", "flight_date"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        target_km = float(data["target_distance_km"])
    except (ValueError, TypeError):
        return jsonify({"error": "target_distance_km must be a number."}), 400

    try:
        flight_date = date.fromisoformat(data["flight_date"])
    except ValueError:
        return jsonify({"error": "Invalid flight_date (YYYY-MM-DD)."}), 400

    db = get_db()

    # ── Resolve airports ──────────────────────────────────────────────────
    takeoff_id = data.get("takeoff_airport", "")
    dest_id = data.get("destination_airport", takeoff_id)
    safety_profile = data.get("safety_profile", "standard")
    soaring_mode = data.get("soaring_mode", "thermal")
    constraints = data.get("constraints")

    takeoff = _resolve_airport(db, takeoff_id)
    if not takeoff:
        return jsonify({"error": f"Takeoff airport not found: {takeoff_id}"}), 404
    dest = _resolve_airport(db, dest_id) if dest_id and dest_id != takeoff_id else takeoff

    # ── Resolve glider (optional) ─────────────────────────────────────────
    glider = None
    glider_id = data.get("glider_id")
    if glider_id:
        glider = _resolve_glider(db, glider_id)

    inputs_snapshot = {
        "takeoff_airport": takeoff.get("name", takeoff_id),
        "takeoff_lat": takeoff["lat"],
        "takeoff_lon": takeoff["lon"],
        "destination_airport": dest.get("name", dest_id) if dest else takeoff.get("name", takeoff_id),
        "destination_lat": dest["lat"] if dest else takeoff["lat"],
        "destination_lon": dest["lon"] if dest else takeoff["lon"],
        "target_distance_km": target_km,
        "flight_date": flight_date.isoformat(),
        "max_duration_hours": data.get("max_duration_hours", 4.0),
        "takeoff_time": data.get("takeoff_time"),
        "glider_id": glider_id,
        "glider_name": glider.get("name") if glider else None,
        "safety_profile": safety_profile,
        "soaring_mode": soaring_mode,
        "constraints": constraints,
        "custom_instructions": (data.get("custom_instructions") or "")[:2000],
    }

    # User's preferred UI language (en, pl, de, cs)
    language = (data.get("language") or "en").strip().lower()
    if language not in ("en", "pl", "de", "cs"):
        language = "en"

    # Create session early so we can update it
    session_id = None
    auto_name = (
        f"{inputs_snapshot['takeoff_airport']} — "
        f"{target_km:.0f}km {soaring_mode} "
        f"({flight_date.isoformat()})"
    )
    try:
        row = db.execute(
            text("""
                INSERT INTO planner_sessions (user_id, name, status, inputs)
                VALUES (:uid, :name, 'generating', :inputs)
                RETURNING id
            """),
            {
                "uid": str(current_user.id),
                "name": auto_name,
                "inputs": json.dumps(inputs_snapshot),
            },
        ).fetchone()
        db.commit()
        if row:
            session_id = str(row[0])
    except Exception:
        logger.exception("Failed to create planner session")
        try:
            db.rollback()
        except Exception:
            pass

    # Track external calls for usage logging
    g._aip_external_calls = {}

    try:
        # ── 1. Weather fetch ──────────────────────────────────────────────
        weather_cells, weather_meta = fetch_weather_grid(
            db,
            takeoff["lat"], takeoff["lon"],
            target_km,
            flight_date,
            dest_lat=dest["lat"] if dest and dest != takeoff else None,
            dest_lon=dest["lon"] if dest and dest != takeoff else None,
        )
        g._aip_external_calls["weather"] = {
            "mesh_points": weather_meta.get("mesh_points", 0),
            "fetched": weather_meta.get("fetched", 0),
            "cached": weather_meta.get("cached", 0),
        }
        # Per-service weather API stats
        api_stats = weather_meta.get("api_stats", {})
        for svc in ("open_meteo", "windy", "imgw"):
            st = api_stats.get(svc)
            if st:
                g._aip_external_calls[svc] = st

        if not weather_cells:
            _update_session(db, session_id, "error",
                            error_message="No weather data available for the task area.")
            return jsonify({
                "status": "error",
                "message": "No weather data available for the task area.",
                "session_id": session_id,
            }), 200

        # Log wind data availability for debugging
        cells_with_wind = [c for c in weather_cells if c.wind_speed_kts is not None and c.wind_dir is not None]
        if cells_with_wind:
            avg_ws = sum(c.wind_speed_kts for c in cells_with_wind) / len(cells_with_wind)
            avg_wd = sum(c.wind_dir for c in cells_with_wind) / len(cells_with_wind)
            logger.info("Wind data: %d/%d cells have wind (avg %.0f° @ %.0fkt)",
                        len(cells_with_wind), len(weather_cells), avg_wd, avg_ws)
        else:
            logger.warning("Wind data: NONE of %d weather cells have wind info", len(weather_cells))

        # ── 2. Airspace check ─────────────────────────────────────────────
        # Pre-fetch airspace zones for the ENTIRE task area once.  The bbox
        # covers takeoff + destination padded by target_km so every candidate
        # route's legs fall inside the pre-fetched zone set.
        from backend.task_planner.airspace import get_airspace_data

        task_center = [(takeoff["lat"], takeoff["lon"])]
        if dest and dest != takeoff:
            task_center.append((dest["lat"], dest["lon"]))

        pre_zones: list = []
        pre_notams: list = []
        try:
            pre_zones, pre_notams = get_airspace_data(
                db, task_center, flight_date,
                buffer_km=max(target_km * 0.8, 30),
            )
            logger.info("Pre-fetched %d airspace zones and %d NOTAMs for task area",
                        len(pre_zones), len(pre_notams))
        except Exception:
            logger.warning("Wide-area airspace pre-fetch failed", exc_info=True)

        airspace_result = None
        try:
            airspace_result = check_task_airspace(
                db, task_center, flight_date, safety_profile, constraints,
                prefetched_zones=(pre_zones, pre_notams),
            )
        except Exception:
            logger.warning("Airspace check failed", exc_info=True)

        airspace_info = None
        if airspace_result:
            airspace_info = {
                "zones_count": len(airspace_result.zones_in_area),
                "conflicts": len(airspace_result.conflicts),
                "has_blocking": airspace_result.has_blocking_conflict,
            }

        # ── 3. Discover waypoints for AI ─────────────────────────────────
        waypoints = discover_waypoints(
            db,
            takeoff["lat"], takeoff["lon"],
            target_km,
            weather_cells,
            safety_profile=safety_profile,
        )
        g._aip_external_calls["waypoints"] = len(waypoints)

        if not waypoints:
            _update_session(db, session_id, "error",
                            error_message="No waypoints found in the task area.")
            return jsonify({
                "status": "error",
                "message": "No waypoints found in the task area.",
                "session_id": session_id,
            }), 200

        # Build weather summary with time-windowed cells for richer LLM context
        timed_cells = weather_meta.get("timed_cells")
        if timed_cells and any(timed_cells.get(tw) for tw in ("morning", "midday", "afternoon")):
            # Use only time-windowed cells to avoid duplicating base cells
            weather_summary = []
            for tw_name in ("morning", "midday", "afternoon"):
                for c in timed_cells.get(tw_name, []):
                    weather_summary.append(c.summary_line())
        else:
            weather_summary = [c.summary_line() for c in weather_cells]

        # Format waypoints for the AI prompt
        waypoint_dicts = []
        for wp in waypoints:
            waypoint_dicts.append({
                "name": wp.name,
                "lat": wp.lat,
                "lon": wp.lon,
                "type": wp.type,
                "distance_km": wp.distance_km,
                "bearing_deg": wp.bearing_deg,
                "icao": wp.icao,
                "summary_line": wp.summary_line(),
                "thermal_index": wp.thermal_index,
                "wind_speed_kts": wp.wind_speed_kts,
                "wind_dir": wp.wind_dir,
                "cloud_base_ft": wp.cloud_base_ft,
            })

        # Format airspace zones for the AI prompt
        airspace_zone_dicts = []
        for zone in pre_zones:
            airspace_zone_dicts.append({
                "name": zone.name,
                "type": zone.type,
                "airspace_class": zone.airspace_class,
                "lower_limit_ft": zone.lower_limit_ft,
                "upper_limit_ft": zone.upper_limit_ft,
                "polygon": zone.polygon,
            })

        # ── 4. Terrain check (use takeoff area as initial estimate) ───────
        terrain_info = None
        try:
            terrain_result = check_task_terrain(
                [(takeoff["lat"], takeoff["lon"])],
                expected_altitude_m=int((weather_cells[0].bl_height or 1500) * 0.8),
            )
            terrain_info = {
                "safe": terrain_result["safe"],
                "max_terrain_m": terrain_result["max_terrain_m"],
            }
        except Exception:
            logger.warning("Terrain check failed", exc_info=True)

        # ── 5. AI route design ────────────────────────────────────────────
        # Pass weather cells for flyability assessment (removed before serialization)
        all_weather_cells = weather_cells[:]
        if timed_cells:
            for tw_cells in timed_cells.values():
                all_weather_cells.extend(tw_cells)
        inputs_snapshot["_weather_cells"] = all_weather_cells

        ai_result = generate_task_routes(
            waypoint_dicts, weather_summary, inputs_snapshot,
            airspace_zones=airspace_zone_dicts,
            terrain_info=terrain_info,
            language=language,
            api_key_override=user_api_key,
            custom_instructions=inputs_snapshot.get("custom_instructions", ""),
        )
        # Remove non-serializable weather cells from snapshot before JSON response
        inputs_snapshot.pop("_weather_cells", None)
        g._aip_external_calls["ai_model"] = ai_result.get("ai_model", "none")
        # Per-provider AI API stats
        ai_stats = ai_result.get("ai_stats", {})
        for attempt in ai_stats.get("attempts", []):
            prov = attempt.get("provider", "unknown")
            g._aip_external_calls[prov] = {
                "calls": 1,
                "ok": 1 if attempt.get("status") == "ok" else 0,
                "errors": 0 if attempt.get("status") == "ok" else 1,
                "total_time_ms": attempt.get("time_ms", 0),
            }

        ai_route = ai_result.get("route")
        if not ai_route:
            _update_session(db, session_id, "error",
                            error_message="AI could not generate a viable route.")
            return jsonify({
                "status": "error",
                "message": "AI could not generate a viable route.",
                "session_id": session_id,
            }), 200

        # ── 6. Validate & snap AI route to real waypoints ─────────────────
        validated = validate_ai_route(
            ai_route,
            takeoff["lat"], takeoff["lon"],
            waypoint_dicts,
        )
        if not validated:
            logger.warning("AI route validation failed — turnpoints don't match available waypoints")
            _update_session(db, session_id, "error",
                            error_message="AI route could not be validated against available waypoints.")
            return jsonify({
                "status": "error",
                "message": "AI route could not be validated. Please try again.",
                "session_id": session_id,
            }), 200

        # ── 7. Re-run terrain check with the actual validated route ──────
        route_points = [(tp["lat"], tp["lon"]) for tp in validated["turnpoints"]]
        if len(route_points) >= 2:
            try:
                terrain_result = check_task_terrain(
                    route_points,
                    expected_altitude_m=int((weather_cells[0].bl_height or 1500) * 0.8),
                )
                terrain_info = {
                    "safe": terrain_result["safe"],
                    "max_terrain_m": terrain_result["max_terrain_m"],
                }
            except Exception:
                logger.warning("Terrain re-check failed for validated route", exc_info=True)

        # ── 8. Airspace conflict analysis (AI-primary, programmatic fallback) ─
        route_leg_points = (
            [(takeoff["lat"], takeoff["lon"])]
            + [(tp["lat"], tp["lon"]) for tp in validated["turnpoints"]]
            + [(takeoff["lat"], takeoff["lon"])]
        )

        # Programmatic check — authoritative for zone count and blocking flag
        prog_conflicts: list[dict] = []
        try:
            airspace_result = check_task_airspace(
                db, route_leg_points, flight_date, safety_profile, constraints,
                prefetched_zones=(pre_zones, pre_notams),
            )
            airspace_info = {
                "zones_count": len(airspace_result.zones_in_area),
                "conflicts": 0,        # updated below after merging
                "has_blocking": airspace_result.has_blocking_conflict,
                "conflict_list": [],   # populated below
            }
            prog_conflicts = [
                {
                    "zone_name": c.zone_name,
                    "zone_type": c.zone_type,
                    "airspace_class": c.airspace_class,
                    "leg_index": c.leg_index,
                    "suggestion": c.suggestion,
                    "requires_transponder": c.requires_transponder,
                    "requires_flight_plan": c.requires_flight_plan,
                    "is_notam": c.is_notam,
                }
                for c in airspace_result.conflicts
            ]
            logger.info(
                "Programmatic airspace check: %d conflicts (%s), %d zones in area",
                len(prog_conflicts),
                "BLOCKING" if airspace_result.has_blocking_conflict else "advisory",
                len(airspace_result.zones_in_area),
            )
        except Exception:
            logger.warning("Programmatic airspace re-check failed", exc_info=True)
            if airspace_info is None:
                airspace_info = {
                    "zones_count": len(pre_zones),
                    "conflicts": 0,
                    "has_blocking": False,
                    "conflict_list": [],
                }

        # AI-reported conflicts are the primary source of conflict details.
        # The AI reasoned about each leg using the full zone list it received.
        # Enrich each AI conflict with metadata from the pre-fetched zone objects.
        ai_conflicts_raw = ai_result.get("airspace_conflicts") or []
        zone_meta_by_name = {z.name: z for z in pre_zones}

        if ai_conflicts_raw:
            conflict_list: list[dict] = []
            for ac in ai_conflicts_raw:
                if not isinstance(ac, dict):
                    continue
                z_name = ac.get("zone_name", "")
                z_meta = zone_meta_by_name.get(z_name)
                conflict_list.append({
                    "zone_name": z_name,
                    "zone_type": ac.get("zone_type") or (z_meta.type if z_meta else ""),
                    "airspace_class": ac.get("airspace_class") or (z_meta.airspace_class if z_meta else ""),
                    "leg_index": ac.get("leg_index", 0),
                    "suggestion": ac.get("suggestion", ""),
                    "severity": ac.get("severity", "advisory"),
                    "requires_transponder": getattr(z_meta, "requires_transponder", False) if z_meta else False,
                    "requires_flight_plan": getattr(z_meta, "requires_flight_plan", False) if z_meta else False,
                    "is_notam": False,
                })
            is_ai_blocking = any(c.get("severity") == "blocking" for c in conflict_list)
            airspace_info["conflict_list"] = conflict_list
            airspace_info["conflicts"] = len(conflict_list)
            airspace_info["has_blocking"] = airspace_info.get("has_blocking", False) or is_ai_blocking
            logger.info(
                "AI airspace conflicts: %d (programmatic geometric check had %d)",
                len(conflict_list), len(prog_conflicts),
            )
        else:
            # AI returned no conflicts — fall back to programmatic geometric results
            airspace_info["conflict_list"] = prog_conflicts
            airspace_info["conflicts"] = len(prog_conflicts)
            logger.info(
                "AI returned no airspace_conflicts — using programmatic results (%d)",
                len(prog_conflicts),
            )

        # ── 9. Build response ─────────────────────────────────────────────
        # Flight time estimate
        flight_est = estimate_flight_time(
            validated["total_distance_km"],
            glider_polar=glider,
        )

        result = {
            "status": "completed",
            "task": validated,
            "score": ai_result.get("route", {}).get("score", 50),
            "explanation": ai_result.get("explanation", ""),
            "weather_summary": ai_result.get("weather_summary", ""),
            "recommended_takeoff_time": ai_result.get("recommended_takeoff_time"),
            "estimated_duration_hours": (
                ai_result.get("estimated_duration_hours")
                or flight_est["estimated_duration_hours"]
            ),
            "estimated_speed_kmh": (
                ai_result.get("estimated_speed_kmh")
                or flight_est["estimated_speed_kmh"]
            ),
            "safety_notes": ai_result.get("safety_notes", []),
            "ai_model": ai_result.get("ai_model", "none"),
            "alternatives": [],
            "weather_meta": {k: v for k, v in weather_meta.items() if k != "timed_cells"},
            "terrain": terrain_info,
            "airspace": airspace_info,
        }

        # Persist to session
        serializable_meta = {k: v for k, v in weather_meta.items() if k != "timed_cells"}
        _update_session(
            db, session_id, "completed",
            weather_data={"cells": len(weather_cells), "meta": serializable_meta},
            airspace_data=airspace_info,
            result=result,
        )

        result["session_id"] = session_id
        result["inputs"] = inputs_snapshot
        return jsonify(result)

    except Exception as exc:
        logger.exception("Task generation failed")
        _update_session(db, session_id, "error", error_message=str(exc)[:500])
        return jsonify({
            "status": "error",
            "message": f"Task generation failed: {str(exc)[:200]}",
            "session_id": session_id,
        }), 500


# ── Helper functions ─────────────────────────────────────────────────────────

def _resolve_airport(db: Session, identifier: str) -> dict | None:
    """Resolve an airport by ID, ICAO code, or name."""
    if not identifier:
        return None
    row = db.execute(
        text("""
            SELECT id, "icaoCode", name, latitude, longitude, elevation, country, "runwayDirection"
            FROM airports
            WHERE id = :id OR "icaoCode" ILIKE :q OR name ILIKE :q
            LIMIT 1
        """),
        {"id": identifier, "q": identifier},
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "icao": row[1] or "",
        "name": row[2],
        "lat": row[3],
        "lon": row[4],
        "elevation": row[5],
        "country": row[6],
        "runway_direction": row[7],
    }


def _resolve_glider(db: Session, glider_id: str) -> dict | None:
    """Resolve a glider by ID."""
    row = db.execute(
        text("""
            SELECT id, name, max_gross_kg, max_ballast_l, v1_kmh, w1_ms,
                   v2_kmh, w2_ms, v3_kmh, w3_ms, wing_area_m2,
                   reference_mass_kg, handicap, polar_a, polar_b, polar_c
            FROM glider_polars WHERE id = :id
        """),
        {"id": glider_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]), "name": row[1], "max_gross_kg": row[2],
        "max_ballast_l": row[3], "v1_kmh": row[4], "w1_ms": row[5],
        "v2_kmh": row[6], "w2_ms": row[7], "v3_kmh": row[8], "w3_ms": row[9],
        "wing_area_m2": row[10], "reference_mass_kg": row[11],
        "handicap": row[12], "polar_a": row[13], "polar_b": row[14], "polar_c": row[15],
    }


def _update_session(
    db: Session,
    session_id: str | None,
    status: str,
    *,
    weather_data: dict | None = None,
    airspace_data: dict | None = None,
    result: dict | None = None,
    error_message: str | None = None,
) -> None:
    """Update a planner session in the DB."""
    if not session_id:
        return
    try:
        db.execute(
            text("""
                UPDATE planner_sessions
                SET status = :status,
                    weather_data = COALESCE(:wd, weather_data),
                    airspace_data = COALESCE(:ad, airspace_data),
                    result = COALESCE(:res, result),
                    error_message = COALESCE(:err, error_message),
                    updated_at = NOW()
                WHERE id = :sid
            """),
            {
                "status": status,
                "wd": json.dumps(weather_data) if weather_data else None,
                "ad": json.dumps(airspace_data) if airspace_data else None,
                "res": json.dumps(result) if result else None,
                "err": error_message,
                "sid": session_id,
            },
        )
        db.commit()
    except Exception:
        logger.warning("Session update failed", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass


# ── Planner sessions (persistence) ───────────────────────────────────────────

@ai_planner_bp.route("/api/planner/sessions", methods=["GET"])
@login_required
def list_sessions():
    """Return the current user's planner sessions (most recent first).

    Includes summary fields extracted from the result JSONB so the frontend
    can render rich history cards without fetching each session individually.
    """
    db = get_db()
    rows = db.execute(
        text("""
            SELECT id, name, status, inputs, created_at, updated_at,
                   result->'score'                          AS score,
                   result->'task'->>'total_distance_km'     AS distance_km,
                   result->'task'->>'description'           AS route_description,
                   result->>'ai_model'                      AS ai_model,
                   result->>'estimated_duration_hours'       AS est_hours,
                   error_message
            FROM planner_sessions
            WHERE user_id = :uid
            ORDER BY updated_at DESC
            LIMIT 50
        """),
        {"uid": str(current_user.id)},
    ).fetchall()
    return jsonify([
        {
            "id": str(r[0]),
            "name": r[1],
            "status": r[2],
            "inputs": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
            "updated_at": r[5].isoformat() if r[5] else None,
            "score": r[6],
            "distance_km": float(r[7]) if r[7] else None,
            "route_description": r[8],
            "ai_model": r[9],
            "est_hours": float(r[10]) if r[10] else None,
            "error_message": (r[11] or "")[:100] if r[11] else None,
        }
        for r in rows
    ])


@ai_planner_bp.route("/api/planner/sessions/<session_id>", methods=["GET"])
@login_required
def get_session(session_id: str):
    """Load a full planner session (inputs + fetched data + result)."""
    db = get_db()
    row = db.execute(
        text("""
            SELECT id, name, status, inputs, weather_data, airspace_data,
                   result, error_message, created_at, updated_at
            FROM planner_sessions
            WHERE id = :sid AND user_id = :uid
        """),
        {"sid": session_id, "uid": str(current_user.id)},
    ).fetchone()
    if not row:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({
        "id": str(row[0]),
        "name": row[1],
        "status": row[2],
        "inputs": row[3],
        "weather_data": row[4],
        "airspace_data": row[5],
        "result": row[6],
        "error_message": row[7],
        "created_at": row[8].isoformat() if row[8] else None,
        "updated_at": row[9].isoformat() if row[9] else None,
    })


@ai_planner_bp.route("/api/planner/sessions/<session_id>", methods=["PATCH"])
@login_required
def update_session(session_id: str):
    """Rename a planner session."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required."}), 400

    db = get_db()
    result = db.execute(
        text("""
            UPDATE planner_sessions
            SET name = :name, updated_at = NOW()
            WHERE id = :sid AND user_id = :uid
        """),
        {"name": name[:255], "sid": session_id, "uid": str(current_user.id)},
    )
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({"success": True})


@ai_planner_bp.route("/api/planner/sessions/<session_id>", methods=["DELETE"])
@login_required
def delete_session(session_id: str):
    """Delete a planner session."""
    db = get_db()
    result = db.execute(
        text("DELETE FROM planner_sessions WHERE id = :sid AND user_id = :uid"),
        {"sid": session_id, "uid": str(current_user.id)},
    )
    db.commit()
    if result.rowcount == 0:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({"success": True})
