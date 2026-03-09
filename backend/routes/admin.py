"""Admin blueprint — /api/admin/*

Routes (all require admin tier):
  GET    /api/admin/users                          — list / search users
  GET    /api/admin/users/<id>                     — user detail + content counts
  PATCH  /api/admin/users/<id>                     — update tier / is_active
  DELETE /api/admin/users/<id>                     — delete user + all content
  GET    /api/admin/users/<id>/content             — list user's files & tasks
  DELETE /api/admin/content/files/<file_id>        — delete a waypoint file
  DELETE /api/admin/content/tasks/<task_id>        — delete a task
  GET    /api/admin/usage/summary                  — AI planner usage analytics
  GET    /api/admin/usage/log                      — paginated usage log
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from backend.db import get_db
from backend.services import admin_service
from backend.services.admin_service import AdminServiceError
from backend.services import usage_service
from backend.utils.auth_decorators import admin_required

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


# ── users ────────────────────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    db = get_db()
    result = admin_service.list_users(
        db,
        q=request.args.get('q', '').strip(),
        tier=request.args.get('tier', '').strip(),
        page=int(request.args.get('page', 1)),
        per_page=int(request.args.get('per_page', 25)),
    )
    return jsonify(result)


@admin_bp.route('/users/<user_id>', methods=['GET'])
@admin_required
def get_user(user_id: str):
    db = get_db()
    user = admin_service.get_user(db, user_id)
    if user is None:
        return jsonify({'error': 'User not found.'}), 404
    d = user.to_dict()
    from sqlalchemy import func
    from backend.models.waypoint_file import WaypointFile
    from backend.models.task import SavedTask
    d['file_count'] = db.query(func.count()).filter(WaypointFile.owner_id == user.id).scalar() or 0
    d['task_count'] = db.query(func.count()).filter(SavedTask.owner_id == user.id).scalar() or 0
    return jsonify(d)


@admin_bp.route('/users/<user_id>', methods=['PATCH'])
@admin_required
def update_user(user_id: str):
    data = request.get_json(silent=True) or {}
    tier = data.get('tier')
    is_active = data.get('is_active')
    db = get_db()
    try:
        user = admin_service.update_user(db, user_id, tier=tier, is_active=is_active)
        db.commit()
        return jsonify(user.to_dict())
    except AdminServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Admin update user error')
        return jsonify({'error': 'Failed to update user.'}), 500


@admin_bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id: str):
    db = get_db()
    try:
        admin_service.delete_user(db, user_id)
        db.commit()
        return jsonify({'success': True})
    except AdminServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Admin delete user error')
        return jsonify({'error': 'Failed to delete user.'}), 500


@admin_bp.route('/users/<user_id>/content', methods=['GET'])
@admin_required
def get_user_content(user_id: str):
    db = get_db()
    try:
        return jsonify(admin_service.get_user_content(db, user_id))
    except AdminServiceError as e:
        return jsonify({'error': str(e)}), 404


# ── content ──────────────────────────────────────────────────────────────────

@admin_bp.route('/content/files/<file_id>', methods=['DELETE'])
@admin_required
def delete_waypoint_file(file_id: str):
    db = get_db()
    try:
        admin_service.delete_waypoint_file(db, file_id)
        db.commit()
        return jsonify({'success': True})
    except AdminServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Admin delete file error')
        return jsonify({'error': 'Failed to delete file.'}), 500


@admin_bp.route('/content/tasks/<task_id>', methods=['DELETE'])
@admin_required
def delete_task(task_id: str):
    db = get_db()
    try:
        admin_service.delete_task(db, task_id)
        db.commit()
        return jsonify({'success': True})
    except AdminServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Admin delete task error')
        return jsonify({'error': 'Failed to delete task.'}), 500


# ── Usage Tracking ───────────────────────────────────────────────────────────

@admin_bp.route('/usage/summary', methods=['GET'])
@admin_required
def usage_summary():
    days = request.args.get('days', 30, type=int)
    days = max(1, min(days, 365))
    db = get_db()
    try:
        summary = usage_service.get_usage_summary(db, days=days)
        return jsonify(summary)
    except Exception:
        logger.exception('Failed to get usage summary')
        return jsonify({'error': 'Failed to retrieve usage summary.'}), 500


@admin_bp.route('/usage/log', methods=['GET'])
@admin_required
def usage_log():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(1, min(per_page, 200))
    endpoint = request.args.get('endpoint') or None
    db = get_db()
    try:
        log = usage_service.get_usage_log(db, page=page, per_page=per_page, endpoint=endpoint)
        return jsonify(log)
    except Exception:
        logger.exception('Failed to get usage log')
        return jsonify({'error': 'Failed to retrieve usage log.'}), 500
