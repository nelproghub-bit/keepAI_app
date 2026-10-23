@echo off
REM Start the network-enabled KeepAI backend using the project virtual environment.
cd /d "%~dp0"
call "%~dp0start_server.bat"
exit /b %errorlevel%
