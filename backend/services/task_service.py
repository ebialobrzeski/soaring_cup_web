"""Saved task CRUD service with tier-limit enforcement."""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.models.task import SavedTask
from backend.models.user import User
from backend.services.user_service import can_save_task, can_set_private

logger = logging.getLogger(__name__)


class TaskServiceError(Exception):
    """Raised for task service validation failures."""


def list_tasks(db: Session, user: User) -> list[SavedTask]:
    """Return all saved tasks owned by *user*."""
    return (
        db.query(SavedTask)
        .filter(SavedTask.owner_id == user.id)
        .order_by(SavedTask.updated_at.desc())
        .all()
    )


def create_task(
    db: Session,
    user: User,
    name: str,
    task_data: dict,
    description: str = '',
    is_public: bool = True,
    total_distance: Optional[float] = None,
    waypoint_file_id: Optional[str] = None,
) -> SavedTask:
    """Persist a new saved task.

    Enforces tier quotas and visibility rules.
    """
    name = name.strip()
    if not name:
        raise TaskServiceError('Task name is required.')
    if len(name) > 255:
        raise TaskServiceError('Task name must be 255 characters or fewer.')
    if not task_data:
        raise TaskServiceError('Task data is required.')

    if not can_save_task(db, user):
        raise TaskServiceError('You have reached your saved task limit. Upgrade to save more.')

    # Free tier: force public
    if not can_set_private(user):
        is_public = True

    existing = (
        db.query(SavedTask)
        .filter(SavedTask.owner_id == user.id, SavedTask.name == name)
        .first()
    )
    if existing:
        raise TaskServiceError(f'A task named "{name}" already exists in your account.')

    wf_id = _parse_uuid(waypoint_file_id)
    task = SavedTask(
        owner_id=user.id,
        name=name,
        description=description or '',
        is_public=is_public,
        task_data=task_data,
        waypoint_file_id=wf_id,
        total_distance=total_distance,
    )
    db.add(task)
    db.flush()
    logger.info('Created task "%s" for user %s', name, user.id)
    return task


def get_task(db: Session, user: User, task_id: str) -> Optional[SavedTask]:
    """Load a saved task owned by *user*. Returns None if not found / not owned."""
    try:
        tid = uuid.UUID(task_id)
    except (ValueError, AttributeError):
        return None
    return (
        db.query(SavedTask)
        .filter(SavedTask.id == tid, SavedTask.owner_id == user.id)
        .first()
    )


def update_task(
    db: Session,
    user: User,
    task_id: str,
    task_data: dict,
    name: Optional[str] = None,
    description: Optional[str] = None,
    total_distance: Optional[float] = None,
) -> SavedTask:
    """Overwrite task data, optionally updating name / description."""
    task = get_task(db, user, task_id)
    if task is None:
        raise TaskServiceError('Task not found.')

    if name is not None:
        name = name.strip()
        if not name:
            raise TaskServiceError('Task name is required.')
        if len(name) > 255:
            raise TaskServiceError('Task name must be 255 characters or fewer.')
        if name != task.name:
            conflict = (
                db.query(SavedTask)
                .filter(SavedTask.owner_id == user.id, SavedTask.name == name)
                .first()
            )
            if conflict:
                raise TaskServiceError(f'A task named "{name}" already exists in your account.')
        task.name = name

    if description is not None:
        task.description = description
    if task_data:
        task.task_data = task_data
    if total_distance is not None:
        task.total_distance = total_distance

    logger.info('Updated task %s for user %s', task_id, user.id)
    return task


def delete_task(db: Session, user: User, task_id: str) -> bool:
    """Delete a saved task owned by *user*. Returns True if deleted, False if not found."""
    task = get_task(db, user, task_id)
    if task is None:
        return False
    db.delete(task)
    logger.info('Deleted task %s for user %s', task_id, user.id)
    return True


def set_visibility(db: Session, user: User, task_id: str, is_public: bool) -> SavedTask:
    """Toggle public/private visibility on a task. Premium-only."""
    if not can_set_private(user):
        raise TaskServiceError('Upgrade to premium to make tasks private.')
    task = get_task(db, user, task_id)
    if task is None:
        raise TaskServiceError('Task not found.')
    task.is_public = is_public
    logger.info('Set task %s visibility to %s for user %s', task_id, is_public, user.id)
    return task


def _parse_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
