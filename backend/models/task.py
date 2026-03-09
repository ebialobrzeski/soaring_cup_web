"""SavedTask model."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class SavedTask(TimestampMixin, Base):
    __tablename__ = 'saved_tasks'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('gen_random_uuid()'),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='TRUE')
    task_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    waypoint_file_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('waypoint_files.id', ondelete='SET NULL'),
        nullable=True,
    )
    total_distance: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': str(self.id),
            'owner_id': str(self.owner_id),
            'name': self.name,
            'description': self.description,
            'is_public': self.is_public,
            'task_data': self.task_data,
            'waypoint_file_id': str(self.waypoint_file_id) if self.waypoint_file_id else None,
            'total_distance': float(self.total_distance) if self.total_distance else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
