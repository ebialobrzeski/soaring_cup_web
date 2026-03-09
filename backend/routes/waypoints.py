"""Waypoints blueprint — /api/waypoints/*

Routes in this blueprint:
  GET    /api/waypoints                   — session waypoints (anon)
  POST   /api/waypoints                   — add to session (anon)
  PUT    /api/waypoints/<idx>             — update session waypoint (anon)
  DELETE /api/waypoints/<idx>             — delete session waypoint (anon)
  GET    /api/waypoints/files             — list saved files (login)
  POST   /api/waypoints/files             — save session → new file (login)
  GET    /api/waypoints/files/<id>        — load file into session (login)
  PUT    /api/waypoints/files/<id>        — overwrite file from session (login)
  DELETE /api/waypoints/files/<id>        — delete saved file (login)
  PATCH  /api/waypoints/files/<id>/visibility  — toggle public/private (premium)
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session
from flask_login import current_user

from backend.db import get_db
from backend.services import waypoint_service
from backend.services.waypoint_service import WaypointServiceError
from backend.utils.auth_decorators import login_required, premium_required

logger = logging.getLogger(__name__)

waypoints_bp = Blueprint('waypoints', __name__, url_prefix='/api/waypoints')

# ── session helpers (imported from app to keep DRY) ───────────────────────────
# These are imported at request time to avoid circular imports.


def _get_session_helpers():
    from app import get_session_waypoints, set_session_waypoints
    return get_session_waypoints, set_session_waypoints


# ── anonymous session routes ──────────────────────────────────────────────────

@waypoints_bp.route('', methods=['GET'])
def get_waypoints():
    get_session_waypoints, _ = _get_session_helpers()
    waypoints = get_session_waypoints()
    return jsonify([wp.to_dict() for wp in waypoints])


@waypoints_bp.route('', methods=['POST'])
def add_waypoint():
    from backend.file_io import get_elevation
    get_session_waypoints, set_session_waypoints = _get_session_helpers()
    from backend.models.legacy import Waypoint
    import flask
    try:
        data = request.get_json()
        if not data.get('elevation') and data.get('latitude') and data.get('longitude'):
            try:
                elevation = get_elevation(data['latitude'], data['longitude'])
                if elevation and elevation > 0:
                    data['elevation'] = f'{elevation}m'
            except Exception as e:
                logger.warning('Could not fetch elevation: %s', e)

        waypoint = Waypoint.from_dict(data)
        waypoints = get_session_waypoints()
        waypoints.append(waypoint)
        waypoints.sort(key=lambda w: w.name.lower())
        set_session_waypoints(waypoints)
        return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
    except Exception as e:
        logger.exception('Add waypoint error')
        return jsonify({'success': False, 'error': str(e)}), 400


@waypoints_bp.route('/<int:index>', methods=['PUT'])
def update_waypoint(index):
    from backend.file_io import get_elevation
    get_session_waypoints, set_session_waypoints = _get_session_helpers()
    from backend.models.legacy import Waypoint
    try:
        data = request.get_json()
        waypoints = get_session_waypoints()
        if 0 <= index < len(waypoints):
            original = waypoints[index]
            coords_changed = (
                original.latitude != data.get('latitude')
                or original.longitude != data.get('longitude')
            )
            if (coords_changed or not data.get('elevation')) and data.get('latitude') and data.get('longitude'):
                try:
                    elevation = get_elevation(data['latitude'], data['longitude'])
                    if elevation and elevation > 0:
                        data['elevation'] = f'{elevation}m'
                except Exception as e:
                    logger.warning('Could not fetch elevation: %s', e)

            waypoint = Waypoint.from_dict(data)
            waypoints[index] = waypoint
            waypoints.sort(key=lambda w: w.name.lower())
            set_session_waypoints(waypoints)
            return jsonify({'success': True, 'waypoint': waypoint.to_dict()})
        else:
            return jsonify({'success': False, 'error': 'Waypoint index out of range'}), 404
    except Exception as e:
        logger.exception('Update waypoint error')
        return jsonify({'success': False, 'error': str(e)}), 400


@waypoints_bp.route('/<int:index>', methods=['DELETE'])
def delete_waypoint(index):
    get_session_waypoints, set_session_waypoints = _get_session_helpers()
    try:
        waypoints = get_session_waypoints()
        if 0 <= index < len(waypoints):
            deleted = waypoints.pop(index)
            set_session_waypoints(waypoints)
            return jsonify({'success': True, 'deleted': deleted.to_dict()})
        else:
            return jsonify({'success': False, 'error': 'Waypoint index out of range'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ── saved file routes (requires login) ───────────────────────────────────────

@waypoints_bp.route('/files', methods=['GET'])
@login_required
def list_files():
    db = get_db()
    files = waypoint_service.list_files(db, current_user)
    return jsonify([f.to_dict() for f in files])


@waypoints_bp.route('/files', methods=['POST'])
@login_required
def create_file():
    get_session_waypoints, _ = _get_session_helpers()
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    description = data.get('description', '')
    is_public = bool(data.get('is_public', True))
    waypoints_data = data.get('waypoints')

    # Use session waypoints if not provided explicitly
    if waypoints_data is None:
        waypoints_data = [wp.to_dict() for wp in get_session_waypoints()]

    db = get_db()
    try:
        wf = waypoint_service.create_file(db, current_user, name, waypoints_data, description, is_public)
        db.commit()
        return jsonify(wf.to_dict()), 201
    except WaypointServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Create waypoint file error')
        return jsonify({'error': 'Failed to save waypoint file.'}), 500


@waypoints_bp.route('/files/<file_id>', methods=['GET'])
@login_required
def get_file(file_id):
    get_session_waypoints, set_session_waypoints = _get_session_helpers()
    from backend.models.legacy import Waypoint
    db = get_db()
    wf = waypoint_service.get_file(db, current_user, file_id)
    if wf is None:
        return jsonify({'error': 'Waypoint file not found.'}), 404

    # Load entries into the session
    entries = list(wf.entries.order_by('sort_order'))
    wps = [
        Waypoint(
            name=e.name,
            code=e.code or '',
            country=e.country or '',
            latitude=float(e.latitude),
            longitude=float(e.longitude),
            elevation=f'{e.elevation}m' if e.elevation else '',
            style=e.style,
            runway_direction=e.runway_direction or 0,
            runway_length=e.runway_length or 0,
            runway_width=e.runway_width or 0,
            frequency=e.frequency or '',
            description=e.description or '',
        )
        for e in entries
    ]
    set_session_waypoints(wps)
    session['current_filename'] = wf.name + '.cup'
    return jsonify({'file': wf.to_dict(), 'waypoints': [wp.to_dict() for wp in wps]})


@waypoints_bp.route('/files/<file_id>', methods=['PUT'])
@login_required
def update_file(file_id):
    get_session_waypoints, _ = _get_session_helpers()
    data = request.get_json(silent=True) or {}
    name = data.get('name')
    description = data.get('description')
    waypoints_data = data.get('waypoints')

    if waypoints_data is None:
        waypoints_data = [wp.to_dict() for wp in get_session_waypoints()]

    db = get_db()
    try:
        wf = waypoint_service.update_file(db, current_user, file_id, waypoints_data, name, description)
        db.commit()
        return jsonify(wf.to_dict())
    except WaypointServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Update waypoint file error')
        return jsonify({'error': 'Failed to update waypoint file.'}), 500


@waypoints_bp.route('/files/<file_id>', methods=['DELETE'])
@login_required
def delete_file(file_id):
    db = get_db()
    deleted = waypoint_service.delete_file(db, current_user, file_id)
    if not deleted:
        return jsonify({'error': 'Waypoint file not found.'}), 404
    db.commit()
    return '', 204


@waypoints_bp.route('/files/<file_id>/visibility', methods=['PATCH'])
@premium_required
def set_visibility(file_id):
    data = request.get_json(silent=True) or {}
    is_public = data.get('is_public')
    if is_public is None:
        return jsonify({'error': 'is_public is required.'}), 400

    db = get_db()
    try:
        wf = waypoint_service.set_visibility(db, current_user, file_id, bool(is_public))
        db.commit()
        return jsonify(wf.to_dict())
    except WaypointServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Set waypoint file visibility error')
        return jsonify({'error': 'Failed to update visibility.'}), 500
