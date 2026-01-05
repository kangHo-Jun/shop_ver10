@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo Shop Automation Setup Tool (V8.1)
echo ==================================================

echo [1/3] Python Version Check...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

echo [2/3] Setting up Virtual Environment...
if not exist .venv (
    python -m venv .venv
)

echo [3/3] Installing Requirements...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo ==================================================
echo Setup complete!
echo ==================================================
pause
