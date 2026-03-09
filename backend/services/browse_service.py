"""Browse / search service for public waypoint files and tasks."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.models.task import SavedTask
from backend.models.user import User
from backend.models.waypoint_file import WaypointEntry, WaypointFile

logger = logging.getLogger(__name__)

_MAX_PER_PAGE = 100
_DEFAULT_PER_PAGE = 20


def browse_waypoint_files(
    db: Session,
    current_user: Optional[User],
    q: str = '',
    country: str = '',
    owner: str = '',
    mine: bool = False,
    page: int = 1,
    per_page: int = _DEFAULT_PER_PAGE,
    sort: str = 'newest',
) -> dict:
    """Search public waypoint files (and current user's private ones if logged in).

    Returns a dict with ``items``, ``total``, ``page``, ``per_page``.
    """
    per_page = max(1, min(per_page, _MAX_PER_PAGE))
    page = max(1, page)

    query = db.query(WaypointFile)

    if mine and current_user:
        query = query.filter(WaypointFile.owner_id == current_user.id)
    elif current_user:
        # Logged-in: public files + own private files
        query = query.filter(
            or_(WaypointFile.is_public == True, WaypointFile.owner_id == current_user.id)  # noqa: E712
        )
    else:
        query = query.filter(WaypointFile.is_public == True)  # noqa: E712

    if q:
        q_like = f'%{q}%'
        # Search by file name or description; subquery for waypoint names
        name_match = WaypointFile.name.ilike(q_like)
        desc_match = WaypointFile.description.ilike(q_like)
        entry_subq = (
            db.query(WaypointEntry.file_id)
            .filter(WaypointEntry.name.ilike(q_like))
            .subquery()
        )
        query = query.filter(
            or_(name_match, desc_match, WaypointFile.id.in_(entry_subq))
        )

    if country:
        country_like = f'%{country}%'
        country_subq = (
            db.query(WaypointEntry.file_id)
            .filter(WaypointEntry.country.ilike(country_like))
            .subquery()
        )
        query = query.filter(WaypointFile.id.in_(country_subq))

    if owner:
        owner_subq = (
            db.query(User.id)
            .filter(User.display_name.ilike(f'%{owner}%'))
            .subquery()
        )
        query = query.filter(WaypointFile.owner_id.in_(owner_subq))

    total = query.count()

    if sort == 'name':
        query = query.order_by(WaypointFile.name.asc())
    elif sort == 'waypoint_count':
        query = query.order_by(WaypointFile.waypoint_count.desc())
    else:
        query = query.order_by(WaypointFile.created_at.desc())

    offset = (page - 1) * per_page
    files = query.offset(offset).limit(per_page).all()

    # Load owner display names in bulk
    owner_ids = {f.owner_id for f in files}
    owners = {u.id: u.display_name for u in db.query(User).filter(User.id.in_(owner_ids)).all()}

    items = []
    for f in files:
        is_mine = bool(current_user and f.owner_id == current_user.id)
        items.append({
            'id': str(f.id),
            'name': f.name,
            'description': f.description,
            'owner_name': owners.get(f.owner_id, 'Unknown'),
            'is_public': f.is_public,
            'is_mine': is_mine,
            'waypoint_count': f.waypoint_count,
            'created_at': f.created_at.isoformat() if f.created_at else None,
            'country_codes': f.country_codes,
            'bbox': f.bbox,
        })

    return {'items': items, 'total': total, 'page': page, 'per_page': per_page}


def browse_tasks(
    db: Session,
    current_user: Optional[User],
    q: str = '',
    owner: str = '',
    mine: bool = False,
    page: int = 1,
    per_page: int = _DEFAULT_PER_PAGE,
    sort: str = 'newest',
) -> dict:
    """Search public saved tasks (and current user's private ones if logged in).

    Returns a dict with ``items``, ``total``, ``page``, ``per_page``.
    """
    per_page = max(1, min(per_page, _MAX_PER_PAGE))
    page = max(1, page)

    query = db.query(SavedTask)

    if mine and current_user:
        query = query.filter(SavedTask.owner_id == current_user.id)
    elif current_user:
        query = query.filter(
            or_(SavedTask.is_public == True, SavedTask.owner_id == current_user.id)  # noqa: E712
        )
    else:
        query = query.filter(SavedTask.is_public == True)  # noqa: E712

    if q:
        q_like = f'%{q}%'
        query = query.filter(
            or_(SavedTask.name.ilike(q_like), SavedTask.description.ilike(q_like))
        )

    if owner:
        owner_subq = (
            db.query(User.id)
            .filter(User.display_name.ilike(f'%{owner}%'))
            .subquery()
        )
        query = query.filter(SavedTask.owner_id.in_(owner_subq))

    total = query.count()

    if sort == 'name':
        query = query.order_by(SavedTask.name.asc())
    elif sort == 'distance':
        query = query.order_by(SavedTask.total_distance.desc())
    else:
        query = query.order_by(SavedTask.created_at.desc())

    offset = (page - 1) * per_page
    tasks = query.offset(offset).limit(per_page).all()

    owner_ids = {t.owner_id for t in tasks}
    owners = {u.id: u.display_name for u in db.query(User).filter(User.id.in_(owner_ids)).all()}

    items = []
    for t in tasks:
        td = t.task_data or {}
        is_mine = bool(current_user and t.owner_id == current_user.id)
        raw_points = td.get('points', [])
        # Compact lat/lon list for minimap rendering in the browser
        minimap_points = [
            {'lat': p['waypoint']['latitude'], 'lon': p['waypoint']['longitude']}
            for p in raw_points
            if isinstance(p, dict) and isinstance(p.get('waypoint'), dict)
            and 'latitude' in p['waypoint'] and 'longitude' in p['waypoint']
        ]
        items.append({
            'id': str(t.id),
            'name': t.name,
            'description': t.description,
            'owner_name': owners.get(t.owner_id, 'Unknown'),
            'is_public': t.is_public,
            'is_mine': is_mine,
            'total_distance': float(t.total_distance) if t.total_distance else None,
            'turnpoint_count': len(raw_points),
            'created_at': t.created_at.isoformat() if t.created_at else None,
            'bbox': t.bbox,
            'points': minimap_points,
        })

    return {'items': items, 'total': total, 'page': page, 'per_page': per_page}
