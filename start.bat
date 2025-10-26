@echo off
REM Startup script for Soaring CUP File Editor Web Application (Windows)

echo Starting Soaring CUP File Editor Web Application...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if requirements are installed
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing Python dependencies...
    pip install -r requirements.txt
)

REM Create uploads directory if it doesn't exist
if not exist uploads mkdir uploads

REM Start the Flask application
echo Starting web server on http://localhost:5000
echo Press Ctrl+C to stop the server
python app.py

pause