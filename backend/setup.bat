@echo off
REM ==========================================================================
REM  FraudShield - one-time setup (Windows)
REM  Creates the Python venv, installs packages, creates the MySQL databases,
REM  builds all tables / views / triggers / stored procedures, loads the demo
REM  data, and installs the frontend packages.
REM  Safe to run again: every step skips what already exists.
REM ==========================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8

echo.
echo === FraudShield setup ===
echo.

REM -- 1. Find Python 3.11+ -------------------------------------------------
set "PY="
for %%V in (3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [X] Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/
    echo     and tick "Add python.exe to PATH" during installation.
    goto :fail
)
echo [1/7] Using %PY%

REM -- 2. Virtual environment + packages ------------------------------------
if not exist venv (
    %PY% -m venv venv || goto :fail
)
call venv\Scripts\activate.bat
echo [2/7] Installing Python packages (first time takes a few minutes)...
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt || goto :fail

REM -- 3. Settings ----------------------------------------------------------
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo [!] A new settings file was created: backend\.env
    echo     Put your MySQL root password in the DB_PASSWORD line, save, and run setup.bat again.
    notepad .env
    goto :fail
)
echo [3/7] Settings found in .env

REM -- 4. Databases ---------------------------------------------------------
echo [4/7] Creating databases fraud_sql and fraud_sql_test (if missing)...
flask create-db || goto :dbfail

REM -- 5. Tables, indexes, views, triggers, procedures ----------------------
echo [5/7] Building tables and the SQL fraud engine...
flask db upgrade || goto :fail
flask init-db-objects || goto :fail

REM -- 6. Demo data ---------------------------------------------------------
echo [6/7] Loading demo data (200 customers, 90 days of payments, Ravi's story)...
flask seed || goto :fail

REM -- 7. Frontend packages -------------------------------------------------
echo [7/7] Installing frontend packages...
where npm >nul 2>&1
if errorlevel 1 (
    echo [!] Node.js was not found, so the frontend was skipped. Install Node.js 18+ from https://nodejs.org
    echo     then run frontend\start_frontend.bat - it installs what it needs.
) else (
    pushd ..\frontend
    if not exist .env copy .env.example .env >nul
    call npm install --no-audit --no-fund || (popd & goto :fail)
    popd
)

echo.
echo === Setup complete ===
echo Start everything with start_all.bat (in the project folder), then open http://localhost:5173
echo Demo logins: admin / Admin@123   risk / Risk@123   analyst / Analyst@123
echo.
pause
exit /b 0

:dbfail
echo.
echo [X] Could not connect to MySQL. Check that:
echo     - the MySQL80 service is running (Windows key ^> "Services" ^> MySQL80 ^> Start)
echo     - DB_PASSWORD in backend\.env is your MySQL root password (special characters like @ are fine)
echo     - DB_HOST is 127.0.0.1 and DB_PORT is 3306
echo.
:fail
echo.
echo Setup stopped. Fix the message above and run setup.bat again.
pause
exit /b 1
