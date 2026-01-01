@echo off
REM Stock Dashboard - Quick Setup for Windows
REM This script automates the setup process for Windows users

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   Stock Dashboard - Windows Setup Script
echo ============================================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.10+ from https://www.python.org
    pause
    exit /b 1
)

echo Step 1: Checking Python version...
python --version
echo.

REM Create virtual environment
echo Step 2: Creating virtual environment...
if exist venv (
    echo Virtual environment already exists. Skipping creation.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo Error: Failed to create virtual environment
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
)
echo.

REM Activate virtual environment
echo Step 3: Activating virtual environment...
call venv\Scripts\activate.bat
echo Virtual environment activated.
echo.

REM Upgrade pip
echo Step 4: Upgrading pip...
python -m pip install --upgrade pip -q
echo pip upgraded.
echo.

REM Install requirements
echo Step 5: Installing dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo Error: Failed to install requirements
    pause
    exit /b 1
)
echo Dependencies installed successfully.
echo.

REM Run verification
echo Step 6: Verifying installation...
python test_setup.py
if errorlevel 1 (
    echo Warning: Some verification checks failed.
    echo Please review the output above.
) else (
    echo.
    echo ============================================================
    echo   Setup Complete! 
    echo ============================================================
    echo.
    echo Your virtual environment is ready to use.
    echo.
    echo Next steps:
    echo   1. Virtual environment is activated (venv is active)
    echo   2. Create .env file with NEWS_API_KEY if needed
    echo   3. Run: python run_dashboard_interactive_host.py
    echo   4. Open browser to: http://127.0.0.1:8050
    echo.
    echo To deactivate virtual environment later, run: deactivate
    echo.
    pause
)

endlocal
