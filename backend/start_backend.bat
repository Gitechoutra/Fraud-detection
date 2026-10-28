@echo off
REM Starts the FraudShield API on http://localhost:5000 (Waitress, with the
REM background scheduler). For auto-reload while editing code, run
REM "python app.py" instead.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
if not exist venv (
    echo The backend is not set up yet. Run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo FraudShield API starting on http://localhost:5000  (Ctrl+C to stop)
python wsgi.py
pause
