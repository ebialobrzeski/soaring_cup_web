"""Admin service — user management and content oversight."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.task import SavedTask
from backend.models.user import User
from backend.models.waypoint_file import WaypointFile

logger = logging.getLogger(__name__)

_VALID_TIERS = frozenset({'free', 'premium', 'admin'})
_MAX_PER_PAGE = 100
_DEFAULT_PER_PAGE = 25


class AdminServiceError(Exception):
    """Raised for admin service validation failures."""


# ── users ────────────────────────────────────────────────────────────────────

def list_users(
    db: Session,
    q: str = '',
    tier: str = '',
    page: int = 1,
    per_page: int = _DEFAULT_PER_PAGE,
) -> dict:
    """Return paginated user list with optional search and tier filter.

    Each item includes content counts.
    """
    per_page = max(1, min(per_page, _MAX_PER_PAGE))
    page = max(1, page)

    query = db.query(User)

    if q:
        like = f'%{q}%'
        query = query.filter(
            or_(User.email.ilike(like), User.display_name.ilike(like))
        )
    if tier and tier in _VALID_TIERS:
        query = query.filter(User.tier == tier)

    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    # Attach content counts in a single pass
    user_ids = [u.id for u in users]
    file_counts: dict[uuid.UUID, int] = {}
    task_counts: dict[uuid.UUID, int] = {}
    if user_ids:
        for uid, cnt in db.query(WaypointFile.owner_id, func.count()).filter(
            WaypointFile.owner_id.in_(user_ids)
        ).group_by(WaypointFile.owner_id).all():
            file_counts[uid] = cnt
        for uid, cnt in db.query(SavedTask.owner_id, func.count()).filter(
            SavedTask.owner_id.in_(user_ids)
        ).group_by(SavedTask.owner_id).all():
            task_counts[uid] = cnt

    items = []
    for u in users:
        d = u.to_dict()
        d['file_count'] = file_counts.get(u.id, 0)
        d['task_count'] = task_counts.get(u.id, 0)
        items.append(d)

    return {'items': items, 'total': total, 'page': page, 'per_page': per_page}


def get_user(db: Session, user_id: str) -> Optional[User]:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None
    return db.query(User).filter(User.id == uid).first()


def update_user(db: Session, user_id: str, tier: Optional[str], is_active: Optional[bool]) -> User:
    """Change a user's tier and/or active status. Returns updated user."""
    user = get_user(db, user_id)
    if user is None:
        raise AdminServiceError('User not found.')
    if tier is not None:
        if tier not in _VALID_TIERS:
            raise AdminServiceError(f'Invalid tier "{tier}". Must be one of: {", ".join(sorted(_VALID_TIERS))}.')
        user.tier = tier
    if is_active is not None:
        user.is_active = bool(is_active)
    db.flush()
    logger.info('Admin updated user %s: tier=%s is_active=%s', user.email, user.tier, user.is_active)
    return user


def delete_user(db: Session, user_id: str) -> None:
    """Delete a user and all their content (cascade via DB FK)."""
    user = get_user(db, user_id)
    if user is None:
        raise AdminServiceError('User not found.')
    email = user.email
    db.delete(user)
    db.flush()
    logger.info('Admin deleted user %s', email)


# ── content ──────────────────────────────────────────────────────────────────

def get_user_content(db: Session, user_id: str) -> dict:
    """Return all waypoint files and tasks owned by the user."""
    user = get_user(db, user_id)
    if user is None:
        raise AdminServiceError('User not found.')

    files = (
        db.query(WaypointFile)
        .filter(WaypointFile.owner_id == user.id)
        .order_by(WaypointFile.updated_at.desc())
        .all()
    )
    tasks = (
        db.query(SavedTask)
        .filter(SavedTask.owner_id == user.id)
        .order_by(SavedTask.updated_at.desc())
        .all()
    )

    return {
        'user': user.to_dict(),
        'files': [f.to_dict() for f in files],
        'tasks': [t.to_dict() for t in tasks],
    }


def delete_waypoint_file(db: Session, file_id: str) -> None:
    try:
        fid = uuid.UUID(file_id)
    except (ValueError, AttributeError):
        raise AdminServiceError('Invalid file ID.')
    wf = db.query(WaypointFile).filter(WaypointFile.id == fid).first()
    if wf is None:
        raise AdminServiceError('Waypoint file not found.')
    db.delete(wf)
    db.flush()
    logger.info('Admin deleted waypoint file %s ("%s")', file_id, wf.name)


def delete_task(db: Session, task_id: str) -> None:
    try:
        tid = uuid.UUID(task_id)
    except (ValueError, AttributeError):
        raise AdminServiceError('Invalid task ID.')
    task = db.query(SavedTask).filter(SavedTask.id == tid).first()
    if task is None:
        raise AdminServiceError('Task not found.')
    db.delete(task)
    db.flush()
    logger.info('Admin deleted task %s ("%s")', task_id, task.name)
