#!/bin/bash
# Startup script for Soaring CUP File Editor Web Application

echo "Starting Soaring CUP File Editor Web Application..."

# Check if Python is available
if ! command -v python &> /dev/null
then
    echo "Python is not installed or not in PATH"
    exit 1
fi

# Check if requirements are installed
if ! python -c "import flask" &> /dev/null
then
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
fi

# Create uploads directory if it doesn't exist
mkdir -p uploads

# Start the Flask application
echo "Starting web server on http://localhost:5000"
echo "Press Ctrl+C to stop the server"
python app.py