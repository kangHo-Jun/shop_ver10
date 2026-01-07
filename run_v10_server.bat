@echo off
REM ===================================================
REM V10 Auto Server Launcher
REM Distributed Lock Edition
REM ===================================================

echo ========================================
echo    V10 Auto Server Launcher
echo    Distributed Lock Edition
echo ========================================
echo.

REM Check if virtual environment exists
if not exist ".venv" (
    echo [ERROR] Virtual environment not found!
    echo Please run setup_env.bat first.
    pause
    exit /b 1
)

REM Activate virtual environment
echo [1/3] Activating virtual environment...
call .venv\Scripts\activate.bat

REM Check if activation was successful
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)

echo [2/3] Checking dependencies...
python -c "import flask, selenium, gspread" 2>nul
if errorlevel 1 (
    echo [WARNING] Some dependencies might be missing
    echo Installing/updating dependencies...
    pip install -r requirements.txt
)

echo [3/3] Starting V10 Server...
echo.
echo ========================================
echo   Server will start at http://localhost:5080
echo   Press Ctrl+C to stop
echo ========================================
echo.

python v10_auto_server.py

echo.
echo ========================================
echo   V10 Server stopped
echo ========================================
pause
