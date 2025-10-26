#!/bin/bash
# Simple startup script for Soaring CUP Web Editor

echo "Starting Soaring CUP Web Editor..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed or not in PATH"
    exit 1
fi

# Install requirements if needed
if [ ! -f "requirements_installed.flag" ]; then
    echo "Installing Python requirements..."
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to install requirements"
        exit 1
    fi
    touch requirements_installed.flag
fi

# Start the web application
echo "Starting web server..."
echo "Open your browser to: http://localhost:5000"

# Try to open browser automatically
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5000 &
elif command -v open &> /dev/null; then
    open http://localhost:5000 &
fi

python3 app.py