"""Waypoint Generation routes — /api/waypoint-gen/*

Endpoints:
  POST /api/waypoint-gen/generate    — generate waypoints for a bbox + type list
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session

from backend.db import get_db
from backend.services import waypoint_generation_service as svc

logger = logging.getLogger(__name__)

waypoint_gen_bp = Blueprint('waypoint_gen', __name__, url_prefix='/api/waypoint-gen')


# ── routes ────────────────────────────────────────────────────────────────────

@waypoint_gen_bp.route('/generate', methods=['POST'])
def generate():
    """Generate waypoints for a map bounding box.

    Request JSON::
        {
            "bbox": {"min_lat": float, "max_lat": float,
                     "min_lon": float, "max_lon": float},
            "types": ["airports", "outlandings", "obstacles",
                      "cities", "towns", "villages"]
        }

    On success the new waypoints are MERGED into the current session and the
    full updated waypoint list is returned so the frontend can replace
    window.app.waypoints in one step.
    """
    body = request.get_json(silent=True) or {}
    bbox = body.get('bbox', {})
    types = body.get('types', [])

    try:
        min_lat = float(bbox['min_lat'])
        max_lat = float(bbox['max_lat'])
        min_lon = float(bbox['min_lon'])
        max_lon = float(bbox['max_lon'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid bbox. Provide min_lat, max_lat, min_lon, max_lon.'}), 400

    if not isinstance(types, list) or not types:
        return jsonify({'success': False, 'error': 'types must be a non-empty list.'}), 400

    db = get_db()
    result = svc.generate_waypoints(db, min_lat, max_lat, min_lon, max_lon, types)

    return jsonify({
        'success': True,
        'added': len(result['waypoints']),
        'sources': result['sources'],
        'warnings': result.get('warnings', []),
        'waypoints': [wp.to_dict() for wp in result['waypoints']],
    })
