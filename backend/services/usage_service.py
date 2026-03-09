"""AI Planner usage tracking service.

Provides functions to log API usage and retrieve analytics data.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any

from flask import Request, g, request
from sqlalchemy import text

logger = logging.getLogger(__name__)


def log_usage(
    db,
    *,
    endpoint: str,
    method: str = "GET",
    request_params: dict | None = None,
    response_status: int = 200,
    response_time_ms: int | None = None,
    external_calls: list[dict] | None = None,
    error_message: str | None = None,
    user_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert a usage record into ai_planner_usage."""
    try:
        db.execute(
            text("""
                INSERT INTO ai_planner_usage (
                    user_id, endpoint, method, request_params,
                    response_status, response_time_ms, external_calls,
                    error_message, ip_address, user_agent
                ) VALUES (
                    :user_id, :endpoint, :method, :request_params,
                    :response_status, :response_time_ms, :external_calls,
                    :error_message, :ip_address, :user_agent
                )
            """),
            {
                "user_id": user_id,
                "endpoint": endpoint,
                "method": method,
                "request_params": json.dumps(request_params) if request_params else None,
                "response_status": response_status,
                "response_time_ms": response_time_ms,
                "external_calls": json.dumps(external_calls) if external_calls else None,
                "error_message": error_message,
                "ip_address": ip_address,
                "user_agent": user_agent,
            },
        )
        db.commit()
    except Exception:
        logger.exception("Failed to log AI planner usage")
        try:
            db.rollback()
        except Exception:
            pass


def log_request(db, *, response_status: int, response_time_ms: int,
                external_calls: list[dict] | None = None,
                error_message: str | None = None) -> None:
    """Log the current Flask request as a usage record."""
    user_id = None
    if hasattr(g, "user") and g.user:
        user_id = str(g.user.get("id") or g.user.get("user_id", ""))
        if not user_id:
            user_id = None

    # Sanitize request params — remove sensitive fields
    params = dict(request.args)
    if request.is_json:
        body = request.get_json(silent=True) or {}
        params.update({k: v for k, v in body.items() if k not in ("password", "token")})

    log_usage(
        db,
        endpoint=request.path,
        method=request.method,
        request_params=params if params else None,
        response_status=response_status,
        response_time_ms=response_time_ms,
        external_calls=external_calls,
        error_message=error_message,
        user_id=user_id,
        ip_address=request.remote_addr,
        user_agent=(request.user_agent.string or "")[:500],
    )


@contextmanager
def track_external_call(service: str, endpoint: str):
    """Context manager to track an external API call's duration and status.

    Usage:
        calls = []
        with track_external_call("openaip", "/api/airspaces") as tracker:
            resp = requests.get(url)
            tracker["status"] = resp.status_code
        calls.append(tracker)
    """
    tracker: dict[str, Any] = {
        "service": service,
        "endpoint": endpoint,
        "status": None,
        "time_ms": None,
    }
    start = time.perf_counter()
    try:
        yield tracker
    finally:
        tracker["time_ms"] = int((time.perf_counter() - start) * 1000)


def get_usage_summary(db, *, days: int = 30) -> dict:
    """Get aggregate usage statistics for the last N days."""
    since = datetime.utcnow() - timedelta(days=days)

    # Total calls
    row = db.execute(
        text("SELECT COUNT(*) FROM ai_planner_usage WHERE created_at >= :since"),
        {"since": since},
    ).fetchone()
    total_calls = row[0] if row else 0

    # Calls by endpoint
    rows = db.execute(
        text("""
            SELECT endpoint, COUNT(*) as cnt, 
                   AVG(response_time_ms)::int as avg_time,
                   COUNT(*) FILTER (WHERE response_status >= 400) as errors
            FROM ai_planner_usage
            WHERE created_at >= :since
            GROUP BY endpoint
            ORDER BY cnt DESC
        """),
        {"since": since},
    ).fetchall()
    by_endpoint = [
        {"endpoint": r[0], "count": r[1], "avg_time_ms": r[2], "errors": r[3]}
        for r in rows
    ]

    # Calls by day
    rows = db.execute(
        text("""
            SELECT DATE(created_at) as day, COUNT(*) as cnt,
                   COUNT(*) FILTER (WHERE response_status >= 400) as errors
            FROM ai_planner_usage
            WHERE created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY day
        """),
        {"since": since},
    ).fetchall()
    by_day = [
        {"date": str(r[0]), "count": r[1], "errors": r[2]}
        for r in rows
    ]

    # External API calls breakdown (with per-service stats)
    rows = db.execute(
        text("""
            SELECT kv.key as service,
                   COUNT(*) as cnt,
                   SUM((kv.value->>'calls')::int)   FILTER (WHERE kv.value ? 'calls') as total_calls,
                   SUM((kv.value->>'ok')::int)       FILTER (WHERE kv.value ? 'ok')    as total_ok,
                   SUM((kv.value->>'errors')::int)   FILTER (WHERE kv.value ? 'errors') as total_errors,
                   AVG((kv.value->>'total_time_ms')::int) FILTER (WHERE kv.value ? 'total_time_ms') as avg_time
            FROM ai_planner_usage,
                 jsonb_each(external_calls) as kv
            WHERE created_at >= :since
              AND external_calls IS NOT NULL
              AND jsonb_typeof(external_calls) = 'object'
            GROUP BY kv.key
            ORDER BY cnt DESC
        """),
        {"since": since},
    ).fetchall()
    external_apis = [
        {
            "service": r[0],
            "count": r[1],
            "total_calls": r[2],
            "total_ok": r[3],
            "total_errors": r[4],
            "avg_time_ms": int(r[5]) if r[5] is not None else None,
        }
        for r in rows
    ]

    # Top users
    rows = db.execute(
        text("""
            SELECT u.email, COUNT(*) as cnt
            FROM ai_planner_usage apu
            JOIN users u ON u.id = apu.user_id
            WHERE apu.created_at >= :since
              AND apu.user_id IS NOT NULL
            GROUP BY u.email
            ORDER BY cnt DESC
            LIMIT 10
        """),
        {"since": since},
    ).fetchall()
    top_users = [{"email": r[0], "count": r[1]} for r in rows]

    # Recent errors
    rows = db.execute(
        text("""
            SELECT endpoint, response_status, error_message, created_at
            FROM ai_planner_usage
            WHERE created_at >= :since
              AND response_status >= 400
            ORDER BY created_at DESC
            LIMIT 20
        """),
        {"since": since},
    ).fetchall()
    recent_errors = [
        {
            "endpoint": r[0],
            "status": r[1],
            "error": r[2],
            "time": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]

    return {
        "period_days": days,
        "total_calls": total_calls,
        "by_endpoint": by_endpoint,
        "by_day": by_day,
        "external_apis": external_apis,
        "top_users": top_users,
        "recent_errors": recent_errors,
    }


def get_usage_log(db, *, page: int = 1, per_page: int = 50,
                  endpoint: str | None = None) -> dict:
    """Get paginated usage log entries."""
    offset = (page - 1) * per_page
    where = ""
    params: dict[str, Any] = {"limit": per_page, "offset": offset}

    if endpoint:
        where = "WHERE endpoint = :endpoint"
        params["endpoint"] = endpoint

    count_row = db.execute(
        text(f"SELECT COUNT(*) FROM ai_planner_usage {where}"), params
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = db.execute(
        text(f"""
            SELECT id, user_id, endpoint, method, request_params,
                   response_status, response_time_ms, external_calls,
                   error_message, ip_address, created_at
            FROM ai_planner_usage
            {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).fetchall()

    entries = []
    for r in rows:
        entries.append({
            "id": str(r[0]),
            "user_id": str(r[1]) if r[1] else None,
            "endpoint": r[2],
            "method": r[3],
            "request_params": r[4],
            "response_status": r[5],
            "response_time_ms": r[6],
            "external_calls": r[7],
            "error_message": r[8],
            "ip_address": r[9],
            "created_at": r[10].isoformat() if r[10] else None,
        })

    return {
        "entries": entries,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }
