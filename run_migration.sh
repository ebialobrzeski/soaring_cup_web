#!/bin/bash
# Run this script on your NAS to migrate airports and gliders data

echo "=== GlidePlan Data Migration ==="
echo ""
echo "This will copy airports and gliders from:"
echo "  OLD: postgresql://192.168.1.250:5433/gliding_forecast"
echo "  NEW: postgresql://192.168.1.250:5434/gliding_forecast"
echo ""

# Try running from Docker container first (easiest method)
if command -v docker &> /dev/null; then
    echo "Running migration from Docker container..."
    docker exec -it glideplan python /app/migrate_data.py "$@"
    exit $?
fi

# Fallback: run with local Python3
if command -v python3 &> /dev/null; then
    echo "Running migration with local Python3..."
    python3 migrate_data.py "$@"
    exit $?
fi

echo "ERROR: Neither docker nor python3 found!"
echo "Please install Python 3 with psycopg2:"
echo "  sudo apt-get update"
echo "  sudo apt-get install python3 python3-pip"
echo "  pip3 install psycopg2-binary"
exit 1
