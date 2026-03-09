"""
Migration runner — applies pending SQL migrations in order.

Usage:
    python -m backend.migrate          # apply all pending migrations
    python -m backend.migrate --dry    # preview only, no changes applied
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a module
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import DATABASE_URL  # noqa: E402 — must come after sys.path fix

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / 'migrations'


def _get_applied(conn) -> set[str]:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id          SERIAL PRIMARY KEY,
            filename    VARCHAR(255) UNIQUE NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    rows = conn.execute('SELECT filename FROM schema_migrations').fetchall()
    return {row[0] for row in rows}


def run(dry_run: bool = False) -> None:
    if not DATABASE_URL:
        logger.error('DATABASE_URL is not set. Cannot run migrations.')
        sys.exit(1)

    import psycopg2  # type: ignore

    db_url = DATABASE_URL.strip('"').strip("'")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Bootstrap migrations table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id          SERIAL PRIMARY KEY,
                filename    VARCHAR(255) UNIQUE NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()

        cur.execute('SELECT filename FROM schema_migrations ORDER BY filename')
        applied: set[str] = {row[0] for row in cur.fetchall()}

        migration_files = sorted(MIGRATIONS_DIR.glob('*.sql'))

        pending = [f for f in migration_files if f.name not in applied]

        if not pending:
            logger.info('All migrations are up to date.')
            return

        for migration_file in pending:
            logger.info('%s %s', 'DRY RUN —' if dry_run else 'Applying', migration_file.name)
            sql = migration_file.read_text(encoding='utf-8')
            if not dry_run:
                cur.execute(sql)
                cur.execute(
                    'INSERT INTO schema_migrations (filename) VALUES (%s)',
                    (migration_file.name,)
                )
                conn.commit()
                logger.info('Applied %s', migration_file.name)

        if dry_run:
            logger.info('%d migration(s) would be applied.', len(pending))
        else:
            logger.info('%d migration(s) applied successfully.', len(pending))

    except Exception as exc:
        conn.rollback()
        logger.error('Migration failed: %s', exc)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run database migrations.')
    parser.add_argument('--dry', action='store_true', help='Preview migrations without applying them.')
    args = parser.parse_args()
    run(dry_run=args.dry)
