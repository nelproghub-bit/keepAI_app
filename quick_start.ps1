# KeepAI Quick Start - PowerShell Version
# This script starts the backend server and opens the admin dashboard

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  KeepAI Quick Start" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
Write-Host "✓ Checking Python installation..." -ForegroundColor Green
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Python not found!" -ForegroundColor Red
    Write-Host "Please install Python 3.8 or later" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

Write-Host ""
Write-Host "✓ Python is installed" -ForegroundColor Green
Write-Host ""

# Install dependencies if needed
Write-Host "✓ Checking dependencies..." -ForegroundColor Green
pip show uvicorn >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Installing dependencies..." -ForegroundColor Yellow
    pip install -q -r requirements.txt
    Write-Host "  ✓ Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "  ✓ All dependencies are installed" -ForegroundColor Green
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Starting Backend Server..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server will run on: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "API endpoints at: http://127.0.0.1:8000/api" -ForegroundColor Cyan
Write-Host "Documentation at: http://127.0.0.1:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

# Start the server
$env:PYTHONIOENCODING = "utf-8"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
