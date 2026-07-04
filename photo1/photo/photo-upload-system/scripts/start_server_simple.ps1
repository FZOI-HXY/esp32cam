# Simple server startup script

Write-Host "=========================================="
Write-Host "   ESP32-CAM Server Startup"
Write-Host "=========================================="

# Change to backend directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $scriptPath "..\backend"
Set-Location $backendPath

# Check Python
Try {
    python --version 2>&1 | Out-Null
    Write-Host "Python found"
} Catch {
    Write-Host "Python not found"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check dependencies
Write-Host "Checking dependencies..."
Try {
    python -c "import flask, requests" 2>&1 | Out-Null
    Write-Host "Dependencies OK"
} Catch {
    Write-Host "Installing dependencies..."
    pip install -r requirements.txt
}

# Data dirs are auto-created by app.py on startup (data/uploads, data/captures, data/album)

# Start server
Write-Host "Starting server..."
Write-Host "Server will run at http://localhost:5000"
Write-Host "Press Ctrl+C to stop"

Try {
    python app.py
} Catch {
    Write-Host "Server stopped"
}

Read-Host "Press Enter to exit"
