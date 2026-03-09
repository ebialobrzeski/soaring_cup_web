"""Authentication and user-registration service."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from backend.models.user import User

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class AuthError(Exception):
    """Raised for authentication/authorisation failures."""


def _validate_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise AuthError('Invalid email address.')
    return email


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise AuthError('Password must be at least 8 characters.')


def _validate_display_name(name: str) -> str:
    name = name.strip()
    if len(name) < 2 or len(name) > 100:
        raise AuthError('Display name must be between 2 and 100 characters.')
    return name


def register_user(db: Session, email: str, display_name: str, password: str) -> User:
    """Create a new user account. Raises AuthError on validation failure."""
    email = _validate_email(email)
    display_name = _validate_display_name(display_name)
    _validate_password(password)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise AuthError('An account with that email already exists.')

    user = User(
        email=email,
        display_name=display_name,
        password_hash=generate_password_hash(password),
        tier='free',
        is_active=True,
    )
    db.add(user)
    db.flush()  # get the id without committing yet
    logger.info('Registered new user: %s (id=%s)', email, user.id)
    return user


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    """Return the User if credentials are valid, else None."""
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user is None or not user.is_active:
        return None
    if not check_password_hash(user.password_hash, password):
        return None

    user.last_login_at = datetime.now(timezone.utc)
    db.flush()
    logger.info('Authenticated user: %s', email)
    return user


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    """Update a user's password. Raises AuthError if old password is wrong."""
    if not check_password_hash(user.password_hash, old_password):
        raise AuthError('Current password is incorrect.')
    _validate_password(new_password)
    user.password_hash = generate_password_hash(new_password)
    db.flush()
    logger.info('Password changed for user: %s', user.email)


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    """Load a user by UUID string. Returns None if not found or inactive."""
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        return None
    return db.query(User).filter(User.id == uid, User.is_active == True).first()  # noqa: E712
