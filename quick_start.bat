@echo off
echo KeepAI Quick Start
echo ==================
pip install fastapi uvicorn requests python-dotenv python-multipart
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000