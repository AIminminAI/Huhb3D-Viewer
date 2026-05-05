@echo off
chcp 65001 > nul
title Huhb3D All Services Launcher

echo ============================================
echo   Huhb3D Synthetic Data Generator
echo   One-Click Service Start
echo ============================================
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "CONDA_BASE=C:\ProgramData\miniconda3"
set "PYTHON=%CONDA_BASE%\python.exe"

if not exist "%PYTHON%" (
    echo [ERROR] Python not found at %PYTHON%
    echo Please check your Miniconda/Anaconda installation path.
    pause
    exit /b 1
)

echo [0/2] Checking streamlit ...
"%PYTHON%" -m streamlit version > nul 2>&1
if errorlevel 1 (
    echo streamlit not found, installing ...
    "%PYTHON%" -m pip install streamlit
    if errorlevel 1 (
        echo [ERROR] Failed to install streamlit!
        pause
        exit /b 1
    )
)
echo streamlit OK

echo [1/2] Starting Huhb3D Data Generator - app.py (port 8501) ...
start "Huhb3D-DataGenerator" cmd /c %PYTHON% -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false

echo [2/2] Starting AI Agent UI - agent_ui.py (port 8502) ...
start "Huhb3D-AIAgent" cmd /c %PYTHON% -m streamlit run agent_ui.py --server.port 8502 --server.headless true --browser.gatherUsageStats false

echo.
echo ============================================
echo   All services started!
echo.
echo   - Data Generator (Main): http://localhost:8501
echo     Upload CAD / Generation / AI Description
echo.
echo   - AI Agent Chat:         http://localhost:8502
echo.
echo   Run stop_all.bat to stop all services.
echo ============================================
echo.

timeout /t 5 /nobreak > nul
start http://localhost:8501
