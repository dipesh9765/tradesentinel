@echo off
title KitePulse AI - Frontend Client
color 0a
echo ===================================================
echo           KitePulse AI - Frontend Web App
echo ===================================================
cd /d "%~dp0"

REM Check if node_modules exists
if not exist "node_modules" (
    echo [*] node_modules not found. Running npm install...
    call npm install
)

echo [*] Starting Vite Frontend on http://0.0.0.0:5173...
call npm run dev -- --host 0.0.0.0 --port 5173

pause
