@echo off
REM Starts the API (port 5000) and the web app (port 5173) in two windows,
REM then opens the browser. Run backend\setup.bat once before the first start.
setlocal
cd /d "%~dp0"
if not exist backend\venv (
    echo FraudShield is not set up yet. Running backend\setup.bat first...
    call backend\setup.bat || exit /b 1
)
start "FraudShield API (port 5000)" cmd /k "backend\start_backend.bat"
start "FraudShield web app (port 5173)" cmd /k "frontend\start_frontend.bat"
echo Waiting for both servers to start...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173
echo.
echo FraudShield is running:
echo   Web app : http://localhost:5173
echo   API     : http://localhost:5000/health
echo Close the two server windows to stop it.
