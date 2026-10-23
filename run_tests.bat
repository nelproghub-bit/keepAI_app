@echo off
REM KeepAI Student Dashboard - Automated Test Runner
REM This script runs API tests against the backend

echo ========================================
echo KeepAI Student Dashboard - Test Runner
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

echo Python found!
echo.

REM Check if backend is running
echo Checking if backend is running...
curl -s http://127.0.0.1:8000/api/health >nul 2>&1
if errorlevel 1 (
    echo.
    echo WARNING: Backend server does not appear to be running!
    echo Please start the backend first:
    echo.
    echo   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
    echo.
    echo Press any key to continue anyway, or Ctrl+C to exit...
    pause >nul
) else (
    echo Backend is running!
)

echo.
echo Starting API tests...
echo.

REM Run the test script
python test_api.py

echo.
echo ========================================
echo Tests completed!
echo ========================================
echo.
echo Next steps:
echo 1. If tests passed, open student_dashboard.html in browser
echo 2. Login with: arnel / password123
echo 3. Test the UI manually (see TESTING_GUIDE.md)
echo.
pause
