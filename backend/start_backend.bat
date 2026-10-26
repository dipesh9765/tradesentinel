@echo off
title TradeSentinel - Backend Server
color 0b
echo ===================================================
echo           TradeSentinel - Backend Server
echo ===================================================
cd /d "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in %~dp0venv!
    echo Please create the virtual environment first.
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Starting FastAPI Backend on http://0.0.0.0:8000...
venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
