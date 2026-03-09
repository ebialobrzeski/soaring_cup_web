# Data Migration Instructions

This guide explains how to migrate airports and gliders data from your old database (port 5433) to the new GlidePlan database (port 5434).

## Quick Start (Recommended)

### Option 1: Run from Docker Container (Easiest)

Since your GlidePlan container already has Python and psycopg2 installed:

```bash
# SSH into your NAS
ssh Emil@192.168.1.250

# Navigate to the project directory
cd /volume2/docker/soaring_cup_web

# Preview migration (dry run)
docker exec -it glideplan python /app/migrate_data.py --dry

# Run actual migration
docker exec -it glideplan python /app/migrate_data.py
```

### Option 2: Use the Shell Script

```bash
# On your NAS
cd /volume2/docker/soaring_cup_web

# Make script executable
chmod +x run_migration.sh

# Preview migration
./run_migration.sh --dry

# Run actual migration
./run_migration.sh
```

### Option 3: Run Directly with Python3

If you have Python 3 installed on your NAS:

```bash
# Install required package
pip3 install psycopg2-binary

# Run migration
python3 migrate_data.py --dry    # preview
python3 migrate_data.py          # actual migration
```

## What Gets Migrated?

### Airports Table
- ICAO codes, names, coordinates
- Elevation, timezone, country
- Runway directions
- Active status

### Glider Polars Table
- Glider names and manufacturers
- Polar coefficients (a, b, c)
- Performance data (v1/w1, v2/w2, v3/w3)
- Mass specifications (max gross, ballast, empty)
- Wing area and handicaps

## Database Connection Details

- **Old Database**: `postgresql://gliding_user:***@192.168.1.250:5433/gliding_forecast`
- **New Database**: `postgresql://glideplan:***@192.168.1.250:5434/gliding_forecast`

## Behavior

- **Existing Records**: If an airport or glider already exists (matched by ID for airports, name for gliders), it will be UPDATED with data from the old database
- **New Records**: Records that don't exist will be INSERTED
- **Safe**: The old database is never modified (read-only)
- **Dry Run**: Use `--dry` flag to preview what would be migrated without making changes

## Troubleshooting

### Connection Refused
If you get "connection refused" errors:
- Make sure both database containers are running: `docker ps`
- Verify ports are correct: old=5433, new=5434
- Check that you're running the script from the NAS (not your Windows PC)

### Module Not Found
If you get "ModuleNotFoundError: No module named 'psycopg2'":
```bash
pip install psycopg2-binary
# or if using Docker:
docker exec -it glideplan pip install psycopg2-binary
```

### Permission Denied
```bash
chmod +x run_migration.sh
chmod +x migrate_data.py
```

## Verification

After migration, verify the data:

```bash
# Check airports count
docker exec -it postgres psql -U glideplan -d gliding_forecast -c "SELECT COUNT(*) FROM airports;"

# Check gliders count
docker exec -it postgres psql -U glideplan -d gliding_forecast -c "SELECT COUNT(*) FROM glider_polars;"

# Sample some airports
docker exec -it postgres psql -U glideplan -d gliding_forecast -c "SELECT \"icaoCode\", name, country FROM airports LIMIT 10;"

# Sample some gliders
docker exec -it postgres psql -U glideplan -d gliding_forecast -c "SELECT name, max_gross_kg, handicap FROM glider_polars LIMIT 10;"
```

## Next Steps

After successful migration:
1. Test the airports search: Visit http://192.168.1.250:5000 and use the AI planner
2. Test glider selection in the flight planning interface
3. Consider backing up the new database:
   ```bash
   docker exec postgres pg_dump -U glideplan gliding_forecast > backup_$(date +%Y%m%d).sql
   ```
