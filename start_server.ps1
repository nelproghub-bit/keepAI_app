# KeepAI Server Startup Script
Write-Host "Starting KeepAI Server..." -ForegroundColor Green
Write-Host ""
Write-Host "Prerequisites:" -ForegroundColor Yellow
Write-Host "1. Install dependencies: pip install -r requirements.txt"
Write-Host "2. Configure AI provider in .env file (or use default Ollama)"
Write-Host ""
Write-Host "Server will start on: http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "API endpoints will be available at: http://127.0.0.1:8000/api" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Red
Write-Host ""

$env:PYTHONIOENCODING = "utf-8"
$pythonPath = if (Test-Path ".\.venv\Scripts\python.exe") { ".\.venv\Scripts\python.exe" } else { "python" }

try {
    & $pythonPath -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
}
catch {
    Write-Host "Error starting server: $_" -ForegroundColor Red
    Write-Host "Make sure Python and dependencies are installed" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Press Enter to exit"