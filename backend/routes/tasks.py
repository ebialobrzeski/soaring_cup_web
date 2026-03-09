"""Tasks blueprint — /api/tasks/* and task export routes.

Routes:
  GET    /api/tasks                  — list saved tasks (login)
  POST   /api/tasks                  — save task (login)
  GET    /api/tasks/<id>             — load task (login)
  PUT    /api/tasks/<id>             — update task (login)
  DELETE /api/tasks/<id>             — delete task (login)
  PATCH  /api/tasks/<id>/visibility  — toggle public/private (premium)
  POST   /api/task/export            — export task as CUP string (anon)
  POST   /api/task/download          — download task file (anon)
  POST   /api/task/qr                — generate QR download token (anon)
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request, session
from flask_login import current_user

from backend.db import get_db
from backend.services import task_service
from backend.services.task_service import TaskServiceError
from backend.utils.auth_decorators import login_required, premium_required

logger = logging.getLogger(__name__)

tasks_bp = Blueprint('tasks', __name__)


# ── saved task CRUD ───────────────────────────────────────────────────────────

@tasks_bp.route('/api/tasks', methods=['GET'])
@login_required
def list_tasks():
    db = get_db()
    tasks = task_service.list_tasks(db, current_user)
    return jsonify([t.to_dict() for t in tasks])


@tasks_bp.route('/api/tasks', methods=['POST'])
@login_required
def create_task():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    description = data.get('description', '')
    is_public = bool(data.get('is_public', True))
    # Accept either {task_data: {...}} or {points: [...]} for convenience
    if 'task_data' in data:
        task_data = data.get('task_data') or {}
    else:
        task_data = {'points': data.get('points', [])}
    total_distance = data.get('total_distance')
    waypoint_file_id = data.get('waypoint_file_id')

    db = get_db()
    try:
        task = task_service.create_task(
            db, current_user, name, task_data,
            description=description,
            is_public=is_public,
            total_distance=total_distance,
            waypoint_file_id=waypoint_file_id,
        )
        db.commit()
        return jsonify(task.to_dict()), 201
    except TaskServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Create task error')
        return jsonify({'error': 'Failed to save task.'}), 500


@tasks_bp.route('/api/tasks/<task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    db = get_db()
    task = task_service.get_task(db, current_user, task_id)
    if task is None:
        return jsonify({'error': 'Task not found.'}), 404
    return jsonify(task.to_dict())


@tasks_bp.route('/api/tasks/<task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    data = request.get_json(silent=True) or {}
    task_data = data.get('task_data') or {}
    name = data.get('name')
    description = data.get('description')
    total_distance = data.get('total_distance')

    db = get_db()
    try:
        task = task_service.update_task(
            db, current_user, task_id, task_data,
            name=name, description=description, total_distance=total_distance,
        )
        db.commit()
        return jsonify(task.to_dict())
    except TaskServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Update task error')
        return jsonify({'error': 'Failed to update task.'}), 500


@tasks_bp.route('/api/tasks/<task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    db = get_db()
    deleted = task_service.delete_task(db, current_user, task_id)
    if not deleted:
        return jsonify({'error': 'Task not found.'}), 404
    db.commit()
    return '', 204


@tasks_bp.route('/api/tasks/<task_id>/visibility', methods=['PATCH'])
@premium_required
def set_task_visibility(task_id):
    data = request.get_json(silent=True) or {}
    is_public = data.get('is_public')
    if is_public is None:
        return jsonify({'error': 'is_public is required.'}), 400

    db = get_db()
    try:
        task = task_service.set_visibility(db, current_user, task_id, bool(is_public))
        db.commit()
        return jsonify(task.to_dict())
    except TaskServiceError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception:
        db.rollback()
        logger.exception('Set task visibility error')
        return jsonify({'error': 'Failed to update visibility.'}), 500
