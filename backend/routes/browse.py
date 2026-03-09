"""Browse blueprint — /api/browse/*

Routes:
  GET /api/browse/waypoints  — search public waypoint files
  GET /api/browse/tasks      — search public saved tasks
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

from backend.db import get_db
from backend.services import browse_service

logger = logging.getLogger(__name__)

browse_bp = Blueprint('browse', __name__, url_prefix='/api/browse')


@browse_bp.route('/waypoints', methods=['GET'])
def browse_waypoints():
    db = get_db()
    user = current_user if current_user.is_authenticated else None
    result = browse_service.browse_waypoint_files(
        db,
        current_user=user,
        q=request.args.get('q', '').strip(),
        country=request.args.get('country', '').strip(),
        owner=request.args.get('owner', '').strip(),
        mine=request.args.get('mine', '').lower() == 'true',
        page=int(request.args.get('page', 1)),
        per_page=int(request.args.get('per_page', 20)),
        sort=request.args.get('sort', 'newest'),
    )
    return jsonify(result)


@browse_bp.route('/tasks', methods=['GET'])
def browse_tasks():
    db = get_db()
    user = current_user if current_user.is_authenticated else None
    result = browse_service.browse_tasks(
        db,
        current_user=user,
        q=request.args.get('q', '').strip(),
        owner=request.args.get('owner', '').strip(),
        mine=request.args.get('mine', '').lower() == 'true',
        page=int(request.args.get('page', 1)),
        per_page=int(request.args.get('per_page', 20)),
        sort=request.args.get('sort', 'newest'),
    )
    return jsonify(result)
