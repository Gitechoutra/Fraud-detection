@echo off
REM Starts the FraudShield web app on http://localhost:5173
setlocal
cd /d "%~dp0"
where npm >nul 2>&1
if errorlevel 1 (
    echo Node.js was not found. Install Node.js 18 or newer from https://nodejs.org
    pause
    exit /b 1
)
if not exist .env copy .env.example .env >nul
if not exist node_modules (
    echo Installing frontend packages ^(first time only^)...
    call npm install --no-audit --no-fund || (pause & exit /b 1)
)
echo FraudShield web app starting on http://localhost:5173  (Ctrl+C to stop)
call npm run dev
pause
