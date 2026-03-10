"""User tier / quota service."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.config import TIER_LIMITS
from backend.models.user import User
from backend.models.waypoint_file import WaypointFile
from backend.models.task import SavedTask


def get_tier_limits(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS['free'])


def can_save_file(db: Session, user: User) -> bool:
    limits = get_tier_limits(user.tier)
    max_files = limits['max_waypoint_files']
    if max_files is None:
        return True
    count = db.query(WaypointFile).filter(WaypointFile.owner_id == user.id).count()
    return count < max_files


def can_save_task(db: Session, user: User) -> bool:
    limits = get_tier_limits(user.tier)
    max_tasks = limits['max_saved_tasks']
    if max_tasks is None:
        return True
    count = db.query(SavedTask).filter(SavedTask.owner_id == user.id).count()
    return count < max_tasks


def can_set_private(user: User) -> bool:
    return get_tier_limits(user.tier)['can_set_private']


def can_access_ai_planner(user: User) -> bool:
    return get_tier_limits(user.tier)['ai_planner']


def set_user_tier(db: Session, email: str, new_tier: str) -> Optional[User]:
    """Admin-only: set a user's tier by email. Returns updated user or None."""
    if new_tier not in ('free', 'premium', 'admin'):
        raise ValueError(f'Invalid tier: {new_tier}')
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        return None
    user.tier = new_tier
    db.flush()
    return user


def update_preferred_language(db: Session, user: User, lang_code: Optional[str]) -> None:
    """Set or clear a user's preferred UI language."""
    user.preferred_language = lang_code or None
    db.flush()
