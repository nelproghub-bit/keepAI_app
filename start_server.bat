@echo off
REM KeepAI Backend Server Startup Script
REM This script starts the FastAPI backend server using the virtual environment

cls
title KeepAI Backend Server

echo.
echo ==========================================
echo   KeepAI Backend Server
echo ==========================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please set up the virtual environment:
    echo   1. Open Command Prompt here
    echo   2. Run: python -m venv .venv
    echo   3. Run: .\.venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [OK] Virtual environment found
echo.

REM Verify dependencies
echo [*] Checking dependencies...
.\.venv\Scripts\python.exe -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo [!] Installing dependencies...
    .\.venv\Scripts\pip.exe install -q -r requirements.txt
    echo [OK] Dependencies installed
    echo.
)

REM Verify app can load
echo [*] Verifying application...
.\.venv\Scripts\python.exe -c "from app.main import app" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to load application!
    echo.
    .\.venv\Scripts\python.exe -c "from app.main import app"
    pause
    exit /b 1
)

echo [OK] Application ready
echo.

REM Start server
echo ==========================================
echo Starting Server...
echo ==========================================
echo.
echo [INFO] Server will listen on all network interfaces (port 8000)
echo [INFO] Local API: http://127.0.0.1:8000/api
echo [INFO] Network API: http://YOUR-COMPUTER-IP:8000/api
echo [INFO] Documentation: http://127.0.0.1:8000/docs
echo.
echo [INFO] Database: MariaDB at 127.0.0.1:3306
echo [INFO] Database Name: keepai
echo.
echo [INFO] Press Ctrl+C to stop the server
echo.

REM Execute the server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

REM Server exited
echo.
echo ==========================================
echo Server has stopped
echo ==========================================
pause
