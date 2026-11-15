@echo off
setlocal enabledelayedexpansion

title Company Brain

echo.
echo ==================================================
echo           🧠 Starting Company Brain...            
echo ==================================================
echo.

cd /d "%~dp0"

echo [1/4] Freeing ports 8000 and 3000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING 2^>nul') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING 2^>nul') do taskkill /f /pid %%a >nul 2>&1

echo [2/4] Cleaning build cache...
if exist "bi-platform\frontend\.next" rd /s /q "bi-platform\frontend\.next" >nul 2>&1
if not exist "logs" mkdir "logs"

echo [3/4] Starting FastAPI Backend on port 8000...
start /b "Backend" cmd /c "cd backend && set PYTHONPATH=. && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ..\logs\backend.log 2>&1"

echo [4/4] Starting Next.js Frontend on port 3000...
start /b "Frontend" cmd /c "cd bi-platform\frontend && npm run dev > ..\..\logs\frontend.log 2>&1"

echo Waiting for servers to initialize...
timeout /t 3 /nobreak >nul

echo.
echo ================================================================
echo                 🧠 COMPANY BRAIN IS READY!                     
echo ================================================================
echo.
echo   Click any link below or paste into your browser:
echo.
echo   📊 Business Dashboard:   http://localhost:3000
echo   📂 Upload / Import Data: http://localhost:3000/data/
echo   💳 POS Billing & Sales:  http://localhost:3000/billing/
echo   🤖 AI BI Chatbot:        http://localhost:3000/chat/
echo   ⚡ FastAPI Swagger Docs: http://localhost:8000/docs
echo.
echo   Logs are saved to: logs\backend.log and logs\frontend.log
echo.
echo ================================================================
echo   Opening dashboard in your browser...
echo   Press any key or Ctrl+C in this window anytime to stop.
echo ================================================================
echo.

rem Automatically open in default browser on Windows
start "" "http://localhost:3000"

pause >nul

echo.
echo Shutting down Company Brain...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING 2^>nul') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING 2^>nul') do taskkill /f /pid %%a >nul 2>&1
echo Done.
