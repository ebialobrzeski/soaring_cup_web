#!/usr/bin/env pwsh
# Simple startup script for Soaring CUP Web Editor

Write-Host "Starting Soaring CUP Web Editor..." -ForegroundColor Green

# Check if Python is available
try {
    python --version | Out-Null
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Install requirements if needed
if (-not (Test-Path "requirements_installed.flag")) {
    Write-Host "Installing Python requirements..." -ForegroundColor Yellow
    pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to install requirements" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    New-Item -ItemType File -Name "requirements_installed.flag" | Out-Null
}

# Start the web application
Write-Host "Starting web server..." -ForegroundColor Green
Write-Host "Open your browser to: http://localhost:5000" -ForegroundColor Cyan
Start-Process "http://localhost:5000"
python app.py

Read-Host "Press Enter to exit"