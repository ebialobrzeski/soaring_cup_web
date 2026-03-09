"""
Database engine, session factory, and Flask integration for SQLAlchemy.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import scoped_session, sessionmaker, Session

from backend.config import DATABASE_URL

logger = logging.getLogger(__name__)

_engine = None
_session_factory: scoped_session | None = None

_MIGRATIONS_DIR = Path(__file__).parent / 'migrations'


def _run_pending_migrations(engine) -> None:
    """Apply any SQL migration files that have not yet been recorded in schema_migrations."""
    try:
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id          SERIAL PRIMARY KEY,
                    filename    VARCHAR(255) UNIQUE NOT NULL,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ))
            result = conn.execute(text('SELECT filename FROM schema_migrations ORDER BY filename'))
            applied: set[str] = {row[0] for row in result}

        migration_files = sorted(_MIGRATIONS_DIR.glob('*.sql'))
        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            logger.info('Database schema is up to date.')
            return

        for mf in pending:
            logger.info('Applying migration: %s', mf.name)
            sql = mf.read_text(encoding='utf-8')
            with engine.begin() as conn:
                conn.execute(text(sql))
                conn.execute(
                    text('INSERT INTO schema_migrations (filename) VALUES (:fn)'),
                    {'fn': mf.name},
                )
            logger.info('Migration applied: %s', mf.name)

        logger.info('%d migration(s) applied.', len(pending))
    except Exception as exc:
        logger.error('Auto-migration failed: %s', exc, exc_info=True)


def init_db(app) -> None:
    """Initialise the SQLAlchemy engine and bind it to the Flask app lifecycle."""
    global _engine, _session_factory

    if not DATABASE_URL:
        logger.warning('DATABASE_URL is not set — database features will be unavailable.')
        return

    # Strip surrounding quotes that may appear in .env files
    db_url = DATABASE_URL.strip('"').strip("'")

    _engine = create_engine(
        db_url,
        pool_pre_ping=True,       # verify connections before use
        pool_recycle=1800,         # recycle connections every 30 min
        pool_size=5,
        max_overflow=10,
        echo=app.debug,
    )

    factory = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    _session_factory = scoped_session(factory)

    # Tear down the scoped session at the end of each request
    @app.teardown_appcontext
    def shutdown_session(exc=None) -> None:  # noqa: ANN001
        if _session_factory is not None:
            _session_factory.remove()

    logger.info('Database engine initialised.')

    # Apply any pending SQL migrations automatically
    _run_pending_migrations(_engine)


def get_db() -> Session:
    """Return the scoped session for the current request context."""
    if _session_factory is None:
        raise RuntimeError('Database is not initialised. Call init_db(app) first.')
    return _session_factory()


def get_engine():
    """Return the SQLAlchemy engine (may be None if DB not configured)."""
    return _engine


def is_db_available() -> bool:
    """Return True if the DB is configured and reachable."""
    if _engine is None:
        return False
    try:
        with _engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True
    except Exception:
        return False
