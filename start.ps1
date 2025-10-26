# PowerShell startup script for Soaring CUP File Editor Web Application

Write-Host "Starting Soaring CUP File Editor Web Application..." -ForegroundColor Green

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "Python found: $pythonVersion" -ForegroundColor Cyan
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python from https://python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Flask is installed
try {
    python -c "import flask" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Flask not found"
    }
    Write-Host "Dependencies already installed." -ForegroundColor Green
} catch {
    Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
    
    # Try different pip methods
    $pipInstalled = $false
    
    # Try pip directly
    try {
        pip --version 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Installing with pip..." -ForegroundColor Cyan
            pip install -r requirements.txt
            $pipInstalled = $true
        }
    } catch {}
    
    # Try python -m pip if pip didn't work
    if (-not $pipInstalled) {
        try {
            python -m pip --version 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Installing with python -m pip..." -ForegroundColor Cyan
                python -m pip install -r requirements.txt
                $pipInstalled = $true
            }
        } catch {}
    }
    
    if (-not $pipInstalled) {
        Write-Host "ERROR: pip is not available" -ForegroundColor Red
        Write-Host "Please try manually: python -m pip install -r requirements.txt" -ForegroundColor Yellow
        Write-Host "Or: python -m ensurepip --upgrade" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
    
    # Verify installation
    try {
        python -c "import flask" 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Flask still not found"
        }
        Write-Host "Dependencies installed successfully!" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Failed to install Flask dependencies" -ForegroundColor Red
        Write-Host "Please try manually: python -m pip install -r requirements.txt" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# Create uploads directory if it doesn't exist
if (-not (Test-Path "uploads")) {
    New-Item -ItemType Directory -Path "uploads" | Out-Null
    Write-Host "Created uploads directory" -ForegroundColor Cyan
}

# Start the Flask application
Write-Host ""
Write-Host "================================================================" -ForegroundColor Blue
Write-Host "  Soaring CUP File Editor Web Application" -ForegroundColor Blue
Write-Host "================================================================" -ForegroundColor Blue
Write-Host "  Starting web server on http://localhost:5000" -ForegroundColor Green
Write-Host ""
Write-Host "  Open your web browser and navigate to:" -ForegroundColor Yellow
Write-Host "  http://localhost:5000" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Blue
Write-Host ""

try {
    python app.py
} catch {
    Write-Host "Application stopped." -ForegroundColor Yellow
} finally {
    Write-Host ""
    Read-Host "Press Enter to close"
}