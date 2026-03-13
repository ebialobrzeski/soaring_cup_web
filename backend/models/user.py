"""User model and tier enum."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = 'users'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('gen_random_uuid()'),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default='free',
        server_default='free',
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='TRUE')
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    preferred_language: Mapped[Optional[str]] = mapped_column(
        String(10),
        ForeignKey('languages.code', ondelete='SET NULL'),
        nullable=True,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='FALSE')
    verification_code_hash: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_code_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    openrouter_key_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': str(self.id),
            'email': self.email,
            'display_name': self.display_name,
            'tier': self.tier,
            'is_active': self.is_active,
            'email_verified': self.email_verified,
            'preferred_language': self.preferred_language,
            'has_openrouter_key': bool(self.openrouter_key_enc),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }

    # Flask-Login interface
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return str(self.id)
