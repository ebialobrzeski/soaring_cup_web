@echo off
REM Startup script for Soaring CUP File Editor Web Application (Windows)

echo Starting Soaring CUP File Editor Web Application...

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

echo Python found: 
python --version

REM Check if requirements are installed
python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing Python dependencies...
    
    REM Try pip first
    pip --version >nul 2>&1
    if errorlevel 1 (
        echo pip not found in PATH, trying python -m pip...
        python -m pip --version >nul 2>&1
        if errorlevel 1 (
            echo ERROR: pip is not available
            echo Please install pip or use a Python distribution that includes it
            echo Try: python -m ensurepip --upgrade
            pause
            exit /b 1
        ) else (
            echo Installing with python -m pip...
            python -m pip install -r requirements.txt
        )
    ) else (
        echo Installing with pip...
        pip install -r requirements.txt
    )
    
    REM Check if installation was successful
    python -c "import flask" >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Failed to install Flask dependencies
        echo Please try manually: python -m pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo Dependencies installed successfully!
) else (
    echo Dependencies already installed.
)

REM Create uploads directory if it doesn't exist
if not exist uploads mkdir uploads

REM Start the Flask application
echo.
echo ================================================================
echo  Soaring CUP File Editor Web Application
echo ================================================================
echo  Starting web server on http://localhost:5000
echo  
echo  Open your web browser and navigate to:
echo  http://localhost:5000
echo  
echo  Press Ctrl+C to stop the server
echo ================================================================
echo.

python app.py

pause