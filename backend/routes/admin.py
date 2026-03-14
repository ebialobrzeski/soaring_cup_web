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
  GET    /api/admin/airports/stats                 — airport table row counts
  POST   /api/admin/airports/import                — trigger OpenAIP airport import
"""
from __future__ import annotations

import logging
import threading

from flask import Blueprint, jsonify, request, Response, stream_with_context

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


# ── Airport import ───────────────────────────────────────────────────────────

@admin_bp.route('/airports/stats', methods=['GET'])
@admin_required
def airport_stats():
    """Return airport row counts grouped by country."""
    db = get_db()
    from sqlalchemy import text
    rows = db.execute(text(
        'SELECT country, COUNT(*) AS cnt FROM airports GROUP BY country ORDER BY cnt DESC'
    )).fetchall()
    total = sum(r[1] for r in rows)
    return jsonify({
        'total': total,
        'by_country': [{'country': r[0] or '??', 'count': r[1]} for r in rows],
    })


@admin_bp.route('/airports/import', methods=['POST'])
@admin_required
def import_airports():
    """Trigger an OpenAIP airport import and stream progress as newline-delimited JSON.

    Body (JSON, all optional):
      countries: list[str]  — ISO country codes (default: all)
      types:     list[int]  — OpenAIP type IDs (default: [0,1,2,3,4,5,6])
    """
    data = request.get_json(silent=True) or {}
    countries = data.get('countries') or None
    types_raw = data.get('types')
    allowed_types = set(types_raw) if types_raw else None

    from backend.scripts.import_airports_openaip import (
        ALL_COUNTRIES, DEFAULT_TYPES,
        _fetch_airports_for_country, _parse_airport,
    )
    from backend.config import OPENAIP_API_KEY, DATABASE_URL
    import json as _json
    import time as _time
    import psycopg2
    import psycopg2.extras

    if not OPENAIP_API_KEY:
        return jsonify({'error': 'OPENAIP_API_KEY is not configured on this server.'}), 400

    target_countries = countries or ALL_COUNTRIES
    target_types = allowed_types if allowed_types is not None else DEFAULT_TYPES

    def _generate():
        db_url = DATABASE_URL.strip('"').strip("'")
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
        total_upserted = 0
        total_errors = 0

        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = False
            cur = conn.cursor()
        except Exception as exc:
            yield _json.dumps({'type': 'error', 'message': f'DB connection failed: {exc}'}) + '\n'
            return

        yield _json.dumps({
            'type': 'start',
            'total_countries': len(target_countries),
        }) + '\n'

        for i, country in enumerate(target_countries, 1):
            items = _fetch_airports_for_country(country, target_types)
            count = len(items)
            if items:
                rows = [_parse_airport(item) for item in items]
                try:
                    psycopg2.extras.execute_batch(cur, upsert_sql, rows, page_size=100)
                    conn.commit()
                    total_upserted += count
                except Exception as exc:
                    conn.rollback()
                    logger.error('Airport import DB error for %s: %s', country, exc)
                    total_errors += count
                    count = 0

            yield _json.dumps({
                'type': 'progress',
                'country': country,
                'index': i,
                'total': len(target_countries),
                'upserted': count,
                'total_upserted': total_upserted,
                'total_errors': total_errors,
            }) + '\n'
            _time.sleep(0.3)

        cur.close()
        conn.close()

        yield _json.dumps({
            'type': 'done',
            'total_upserted': total_upserted,
            'total_errors': total_errors,
        }) + '\n'

    return Response(
        stream_with_context(_generate()),
        mimetype='application/x-ndjson',
    )
