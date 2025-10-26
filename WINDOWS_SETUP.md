# Windows Setup Guide

## Quick Start (Recommended)

### Option 1: Use PowerShell (Recommended)
1. Right-click on `start.ps1` and select "Run with PowerShell"
2. If you get an execution policy error, open PowerShell as Administrator and run:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
3. Then try running `start.ps1` again

### Option 2: Use Command Prompt
1. Double-click `start.bat`
2. Follow the on-screen instructions

### Option 3: Manual Setup
1. Open Command Prompt or PowerShell in this folder
2. Install dependencies:
   ```
   python -m pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```
4. Open your browser to: http://localhost:5000

## Troubleshooting

### Python Not Found
- Download Python from https://python.org/downloads/
- **IMPORTANT**: During installation, check "Add Python to PATH"
- Restart your command prompt after installation

### pip Not Found
Try these commands in order:
```cmd
python -m ensurepip --upgrade
python -m pip install -r requirements.txt
```

### Permission Errors
- Run Command Prompt or PowerShell as Administrator
- Or install dependencies for current user only:
  ```
  python -m pip install --user -r requirements.txt
  ```

### Port 5000 Already in Use
- Close any other applications using port 5000
- Or edit `app.py` and change the port number:
  ```python
  app.run(debug=True, host='0.0.0.0', port=8080)
  ```

## Requirements
- Python 3.7 or higher
- Internet connection (for elevation data and map tiles)
- Modern web browser (Chrome, Firefox, Edge, Safari)

## First Time Setup
1. Install Python with PATH option checked
2. Run one of the startup scripts
3. Wait for dependencies to install
4. Open http://localhost:5000 in your browser
5. Start editing waypoint files!

## Usage
- Click "Open File" to load .cup or .csv files
- Use "Add Waypoint" to create new waypoints
- Click waypoints on the map to view details
- Export as .cup or .csv when done