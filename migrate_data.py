"""
Data migration script - Copy airports and glider_polars from old database to new.

Usage:
    python migrate_data.py          # migrate all data
    python migrate_data.py --dry    # preview only, no changes
    
    # Run from Docker container:
    docker exec -it glideplan python migrate_data.py --dry
    docker exec -it glideplan python migrate_data.py
    
    # Run on NAS (where databases are running):
    python3 migrate_data.py --dry
    python3 migrate_data.py
"""
import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Database URLs
OLD_DATABASE_URL = "postgresql://gliding_user:w3OXQNu4MVlAgOG@192.168.1.250:5433/gliding_forecast"
NEW_DATABASE_URL = os.getenv('DATABASE_URL') or "postgresql://glideplan:K5IAWWs8kq1!x@192.168.1.250:5434/gliding_forecast"


def migrate_airports(old_conn, new_conn, dry_run=False):
    """Migrate airports table from old database to new."""
    old_cur = old_conn.cursor()
    new_cur = new_conn.cursor()
    
    # Get all airports from old database
    old_cur.execute('SELECT * FROM airports ORDER BY id')
    columns = [desc[0] for desc in old_cur.description]
    rows = old_cur.fetchall()
    
    logger.info("Found %d airports in old database", len(rows))
    
    if dry_run:
        for row in rows[:5]:  # Show first 5 as preview
            airport_dict = dict(zip(columns, row))
            logger.info("  [DRY] %s - %s (%s)", 
                       airport_dict.get('icaoCode', 'N/A'),
                       airport_dict.get('name', 'N/A'),
                       airport_dict.get('country', 'N/A'))
        if len(rows) > 5:
            logger.info("  [DRY] ... and %d more", len(rows) - 5)
        return len(rows)
    
    # Insert into new database
    inserted = 0
    updated = 0
    
    for row in rows:
        airport_dict = dict(zip(columns, row))
        
        # Check if airport already exists
        new_cur.execute('SELECT id FROM airports WHERE id = %s', (airport_dict['id'],))
        exists = new_cur.fetchone()
        
        if exists:
            # Update existing airport
            new_cur.execute('''
                UPDATE airports SET
                    "icaoCode" = %(icaoCode)s,
                    name = %(name)s,
                    latitude = %(latitude)s,
                    longitude = %(longitude)s,
                    elevation = %(elevation)s,
                    timezone = %(timezone)s,
                    country = %(country)s,
                    "isActive" = %(isActive)s,
                    "updatedAt" = NOW(),
                    "runwayDirection" = %(runwayDirection)s
                WHERE id = %(id)s
            ''', airport_dict)
            updated += 1
        else:
            # Insert new airport
            placeholders = ', '.join(['%s'] * len(airport_dict))
            columns_str = ', '.join([f'"{col}"' for col in columns])
            insert_sql = f'INSERT INTO airports ({columns_str}) VALUES ({placeholders})'
            new_cur.execute(insert_sql, list(airport_dict.values()))
            inserted += 1
    
    new_conn.commit()
    logger.info("Airports: %d inserted, %d updated", inserted, updated)
    return inserted + updated


def migrate_gliders(old_conn, new_conn, dry_run=False):
    """Migrate glider_polars table from old database to new."""
    old_cur = old_conn.cursor()
    new_cur = new_conn.cursor()
    
    # Check if glider_polars table exists in old database
    old_cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'glider_polars'
        )
    """)
    table_exists = old_cur.fetchone()[0]
    
    if not table_exists:
        logger.warning("glider_polars table does not exist in old database - skipping")
        return 0
    
    # Get all gliders from old database
    old_cur.execute('SELECT * FROM glider_polars ORDER BY name')
    columns = [desc[0] for desc in old_cur.description]
    rows = old_cur.fetchall()
    
    logger.info("Found %d gliders in old database", len(rows))
    
    if dry_run:
        for row in rows[:5]:  # Show first 5 as preview
            glider_dict = dict(zip(columns, row))
            logger.info("  [DRY] %s (%.0f kg, handicap %s)", 
                       glider_dict.get('name', 'N/A'),
                       glider_dict.get('max_gross_kg', 0),
                       glider_dict.get('handicap', 'N/A'))
        if len(rows) > 5:
            logger.info("  [DRY] ... and %d more", len(rows) - 5)
        return len(rows)
    
    # Insert into new database
    inserted = 0
    updated = 0
    
    for row in rows:
        glider_dict = dict(zip(columns, row))
        
        # Check if glider already exists (by name, not ID since ID is UUID)
        new_cur.execute('SELECT id FROM glider_polars WHERE name = %s', (glider_dict['name'],))
        exists = new_cur.fetchone()
        
        if exists:
            # Update existing glider
            update_fields = [f'"{col}" = %({col})s' for col in columns if col != 'id' and col != 'created_at']
            update_sql = f'UPDATE glider_polars SET {", ".join(update_fields)} WHERE name = %(name)s'
            new_cur.execute(update_sql, glider_dict)
            updated += 1
        else:
            # Insert new glider (let database generate new UUID for id)
            insert_columns = [col for col in columns if col != 'id']
            columns_str = ', '.join([f'"{col}"' for col in insert_columns])
            placeholders = ', '.join([f'%({col})s' for col in insert_columns])
            insert_sql = f'INSERT INTO glider_polars ({columns_str}) VALUES ({placeholders})'
            new_cur.execute(insert_sql, glider_dict)
            inserted += 1
    
    new_conn.commit()
    logger.info("Gliders: %d inserted, %d updated", inserted, updated)
    return inserted + updated


def main(dry_run=False):
    """Main migration function."""
    if not NEW_DATABASE_URL:
        logger.error("DATABASE_URL is not set (check .env file or environment)")
        sys.exit(1)
    
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Install with: pip install psycopg2-binary")
        sys.exit(1)
    
    # Strip quotes from DATABASE_URL if present
    new_db_url = NEW_DATABASE_URL.strip('"').strip("'")
    
    logger.info("Source database: %s", OLD_DATABASE_URL.replace('w3OXQNu4MVlAgOG', '***'))
    logger.info("Target database: %s", new_db_url.replace(new_db_url.split(':')[2].split('@')[0], '***'))
    
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    
    # Connect to both databases
    try:
        logger.info("Connecting to old database...")
        old_conn = psycopg2.connect(OLD_DATABASE_URL)
        old_conn.autocommit = False
        
        logger.info("Connecting to new database...")
        new_conn = psycopg2.connect(new_db_url)
        new_conn.autocommit = False
        
        # Migrate airports
        logger.info("\n=== Migrating Airports ===")
        airports_count = migrate_airports(old_conn, new_conn, dry_run)
        
        # Migrate gliders
        logger.info("\n=== Migrating Glider Polars ===")
        gliders_count = migrate_gliders(old_conn, new_conn, dry_run)
        
        logger.info("\n=== Migration Complete ===")
        logger.info("Total: %d airports, %d gliders", airports_count, gliders_count)
        
    except Exception as e:
        logger.error("Migration failed: %s", e, exc_info=True)
        if not dry_run and 'new_conn' in locals():
            new_conn.rollback()
        sys.exit(1)
    finally:
        if 'old_conn' in locals():
            old_conn.close()
        if 'new_conn' in locals():
            new_conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Migrate data from old database to new.')
    parser.add_argument('--dry', action='store_true', help='Preview only, no changes.')
    args = parser.parse_args()
    main(dry_run=args.dry)
