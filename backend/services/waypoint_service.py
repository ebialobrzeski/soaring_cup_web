"""Waypoint file CRUD service with tier-limit enforcement."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.user import User
from backend.models.waypoint_file import WaypointEntry, WaypointFile
from backend.services.user_service import can_save_file, can_set_private

logger = logging.getLogger(__name__)


class WaypointServiceError(Exception):
    """Raised for waypoint service validation failures."""


def list_files(db: Session, user: User) -> list[WaypointFile]:
    """Return all waypoint files owned by *user*."""
    return (
        db.query(WaypointFile)
        .filter(WaypointFile.owner_id == user.id)
        .order_by(WaypointFile.updated_at.desc())
        .all()
    )


def create_file(
    db: Session,
    user: User,
    name: str,
    waypoints: list[dict],
    description: str = '',
    is_public: bool = True,
) -> WaypointFile:
    """Persist a new waypoint file from a list of waypoint dicts.

    Enforces tier quotas and visibility rules.
    """
    name = name.strip()
    if not name:
        raise WaypointServiceError('File name is required.')
    if len(name) > 255:
        raise WaypointServiceError('File name must be 255 characters or fewer.')

    if not can_save_file(db, user):
        raise WaypointServiceError('You have reached your waypoint file limit. Upgrade to save more.')

    # Free tier: force public
    if not can_set_private(user):
        is_public = True

    existing = (
        db.query(WaypointFile)
        .filter(WaypointFile.owner_id == user.id, WaypointFile.name == name)
        .first()
    )
    if existing:
        raise WaypointServiceError(f'A file named "{name}" already exists in your account.')

    wf = WaypointFile(
        owner_id=user.id,
        name=name,
        description=description or '',
        is_public=is_public,
        waypoint_count=len(waypoints),
    )
    db.add(wf)
    db.flush()

    _replace_entries(db, wf, waypoints)
    logger.info('Created waypoint file "%s" for user %s', name, user.id)
    return wf


def get_file(db: Session, user, file_id: str) -> Optional[WaypointFile]:
    """Load a waypoint file.

    Returns the file if it is owned by *user* OR if it is public.
    *user* may be an anonymous Flask-Login user.
    """
    try:
        fid = uuid.UUID(file_id)
    except (ValueError, AttributeError):
        return None

    from sqlalchemy import or_
    user_id = user.id if user and getattr(user, 'is_authenticated', False) else None

    q = db.query(WaypointFile).filter(WaypointFile.id == fid)
    if user_id:
        q = q.filter(
            or_(WaypointFile.owner_id == user_id, WaypointFile.is_public.is_(True))
        )
    else:
        q = q.filter(WaypointFile.is_public.is_(True))
    return q.first()


def update_file(
    db: Session,
    user: User,
    file_id: str,
    waypoints: list[dict],
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> WaypointFile:
    """Overwrite the entries of an existing waypoint file.

    Optionally rename or update description if provided.
    """
    wf = get_file(db, user, file_id)
    if wf is None:
        raise WaypointServiceError('Waypoint file not found.')

    if name is not None:
        name = name.strip()
        if not name:
            raise WaypointServiceError('File name is required.')
        if len(name) > 255:
            raise WaypointServiceError('File name must be 255 characters or fewer.')
        if name != wf.name:
            conflict = (
                db.query(WaypointFile)
                .filter(WaypointFile.owner_id == user.id, WaypointFile.name == name)
                .first()
            )
            if conflict:
                raise WaypointServiceError(f'A file named "{name}" already exists in your account.')
        wf.name = name

    if description is not None:
        wf.description = description

    _replace_entries(db, wf, waypoints)
    wf.waypoint_count = len(waypoints)
    logger.info('Updated waypoint file %s for user %s', file_id, user.id)
    return wf


def delete_file(db: Session, user: User, file_id: str) -> bool:
    """Delete a waypoint file owned by *user*. Returns True if deleted, False if not found."""
    wf = get_file(db, user, file_id)
    if wf is None:
        return False
    db.delete(wf)
    logger.info('Deleted waypoint file %s for user %s', file_id, user.id)
    return True


def set_visibility(db: Session, user: User, file_id: str, is_public: bool) -> WaypointFile:
    """Toggle public/private visibility on a waypoint file. Premium-only."""
    if not can_set_private(user):
        raise WaypointServiceError('Upgrade to premium to make files private.')
    wf = get_file(db, user, file_id)
    if wf is None:
        raise WaypointServiceError('Waypoint file not found.')
    wf.is_public = is_public
    logger.info('Set waypoint file %s visibility to %s for user %s', file_id, is_public, user.id)
    return wf


# ── internal helpers ──────────────────────────────────────────────────────────


def _replace_entries(db: Session, wf: WaypointFile, waypoints: list[dict]) -> None:
    """Delete existing entries for *wf* and insert fresh ones from *waypoints*.

    Also computes and saves ``bbox`` and ``country_codes`` on *wf*.
    """
    db.query(WaypointEntry).filter(WaypointEntry.file_id == wf.id).delete()
    lats: list[float] = []
    lons: list[float] = []
    countries: set[str] = set()
    for order, wp in enumerate(waypoints):
        lat = float(wp['latitude'])
        lon = float(wp['longitude'])
        lats.append(lat)
        lons.append(lon)
        c = str(wp.get('country', '')).strip()
        if c:
            countries.add(c.upper())
        entry = WaypointEntry(
            file_id=wf.id,
            name=str(wp.get('name', ''))[:255],
            code=str(wp.get('code', ''))[:50] or None,
            country=str(wp.get('country', ''))[:10] or None,
            latitude=lat,
            longitude=lon,
            elevation=_parse_elevation(wp.get('elevation')),
            style=int(wp.get('style', 1)),
            runway_direction=_parse_int(wp.get('runway_direction')),
            runway_length=_parse_int(wp.get('runway_length')),
            runway_width=_parse_int(wp.get('runway_width')),
            frequency=str(wp.get('frequency', ''))[:20] or None,
            description=str(wp.get('description', '')) or None,
            sort_order=order,
        )
        db.add(entry)
    wf.bbox = (
        {'minLat': min(lats), 'maxLat': max(lats), 'minLon': min(lons), 'maxLon': max(lons)}
        if lats else None
    )
    wf.country_codes = ','.join(sorted(countries)) if countries else None
    db.flush()


def _parse_elevation(value) -> Optional[int]:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip().lower().rstrip('mft ')
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _parse_int(value) -> Optional[int]:
    if value is None or value == '' or value == 0:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
