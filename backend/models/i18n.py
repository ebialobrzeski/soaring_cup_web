"""SQLAlchemy models for internationalisation (i18n): languages, keys, translations."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base


class Language(Base):
    __tablename__ = 'languages'

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    native_name: Mapped[str] = mapped_column(String(100), nullable=False)
    flag_emoji: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default='TRUE')
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    translations: Mapped[list['Translation']] = relationship(back_populates='language', cascade='all, delete-orphan')

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'name': self.name,
            'native_name': self.native_name,
            'flag_emoji': self.flag_emoji,
            'is_active': self.is_active,
        }


class TranslationKey(Base):
    __tablename__ = 'translation_keys'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    default_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    translations: Mapped[list['Translation']] = relationship(back_populates='translation_key', cascade='all, delete-orphan')


class Translation(Base):
    __tablename__ = 'translations'
    __table_args__ = (UniqueConstraint('key_id', 'language_code', name='uq_translation_key_lang'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('translation_keys.id', ondelete='CASCADE'),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(
        String(10),
        ForeignKey('languages.code', ondelete='CASCADE'),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    translation_key: Mapped['TranslationKey'] = relationship(back_populates='translations')
    language: Mapped['Language'] = relationship(back_populates='translations')
