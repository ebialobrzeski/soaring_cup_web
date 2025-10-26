@echo off
REM Simple startup script for Soaring CUP Web Editor

echo Starting Soaring CUP Web Editor...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Install requirements if needed
if not exist "requirements_installed.flag" (
    echo Installing Python requirements...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements
        pause
        exit /b 1
    )
    echo. > requirements_installed.flag
)

REM Start the web application
echo Starting web server...
echo Open your browser to: http://localhost:5000
start http://localhost:5000
python app.py

pause