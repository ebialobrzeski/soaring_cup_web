"""WaypointFile and WaypointEntry models."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TimestampMixin


class WaypointFile(TimestampMixin, Base):
    __tablename__ = 'waypoint_files'

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
    waypoint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    entries: Mapped[list['WaypointEntry']] = relationship(
        'WaypointEntry', back_populates='file', cascade='all, delete-orphan', lazy='dynamic'
    )

    def to_dict(self, include_entries: bool = False) -> dict:
        d = {
            'id': str(self.id),
            'owner_id': str(self.owner_id),
            'name': self.name,
            'description': self.description,
            'is_public': self.is_public,
            'waypoint_count': self.waypoint_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_entries:
            d['entries'] = [e.to_dict() for e in self.entries]
        return d


class WaypointEntry(Base):
    __tablename__ = 'waypoint_entries'

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('gen_random_uuid()'),
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('waypoint_files.id', ondelete='CASCADE'),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    elevation: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    style: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    runway_direction: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runway_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    runway_width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    file: Mapped['WaypointFile'] = relationship('WaypointFile', back_populates='entries')

    def to_dict(self) -> dict:
        return {
            'id': str(self.id),
            'file_id': str(self.file_id),
            'name': self.name,
            'code': self.code or '',
            'country': self.country or '',
            'latitude': float(self.latitude),
            'longitude': float(self.longitude),
            'elevation': self.elevation or 0,
            'style': self.style,
            'runway_direction': self.runway_direction or 0,
            'runway_length': self.runway_length or 0,
            'runway_width': self.runway_width or 0,
            'frequency': self.frequency or '',
            'description': self.description or '',
            'sort_order': self.sort_order,
        }
