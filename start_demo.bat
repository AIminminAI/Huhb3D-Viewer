@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Huhb3D Demo - One-Click Startup

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║                                                              ║
echo  ║     Huhb3D Synthetic Data Generator - Demo Launcher          ║
echo  ║     机器人视觉合成数据生成器 - 一键演示启动                   ║
echo  ║                                                              ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "PYTHON="
set "CONDA_BASE="

if exist "C:\ProgramData\miniconda3\python.exe" (
    set "PYTHON=C:\ProgramData\miniconda3\python.exe"
    set "CONDA_BASE=C:\ProgramData\miniconda3"
)
if exist "C:\ProgramData\anaconda3\python.exe" (
    set "PYTHON=C:\ProgramData\anaconda3\python.exe"
    set "CONDA_BASE=C:\ProgramData\anaconda3"
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PYTHON=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
)

where python > nul 2>&1
if errorlevel 1 (
    if "%PYTHON%"=="" (
        echo  [ERROR] Python not found!
        echo  Please install Python 3.8+ from https://www.python.org/downloads/
        echo  Or install Miniconda from https://docs.conda.io/en/latest/miniconda.html
        pause
        exit /b 1
    )
) else (
    if "%PYTHON%"=="" (
        for /f "tokens=*" %%i in ('where python') do set "PYTHON=%%i"
    )
)

echo  [OK] Python: %PYTHON%

echo.
echo  [1/4] Installing dependencies...
"%PYTHON%" -c "import streamlit" > nul 2>&1
if errorlevel 1 (
    echo  Installing streamlit...
    "%PYTHON%" -m pip install streamlit --quiet
)
"%PYTHON%" -c "import PIL" > nul 2>&1
if errorlevel 1 (
    echo  Installing Pillow...
    "%PYTHON%" -m pip install Pillow --quiet
)
"%PYTHON%" -c "import numpy" > nul 2>&1
if errorlevel 1 (
    echo  Installing numpy...
    "%PYTHON%" -m pip install numpy --quiet
)
"%PYTHON%" -c "import cv2" > nul 2>&1
if errorlevel 1 (
    echo  Installing opencv-python...
    "%PYTHON%" -m pip install opencv-python --quiet
)
"%PYTHON%" -c "import requests" > nul 2>&1
if errorlevel 1 (
    echo  Installing requests...
    "%PYTHON%" -m pip install requests --quiet
)
echo  [OK] Core dependencies ready

echo.
echo  [INFO] Optional: cadquery (for STEP topology parsing, ~500MB)
"%PYTHON%" -c "import cadquery" > nul 2>&1
if errorlevel 1 (
    echo  [OPTIONAL] cadquery not installed - STEP topology will not be available
    echo  [OPTIONAL] To install: pip install cadquery
    echo  [OPTIONAL] STL/OBJ files will still work without cadquery
) else (
    echo  [OK] cadquery available (STEP topology enabled)
)

echo.
echo  [2/4] Checking C++ rendering engine...
set "RENDER_EXE="
if exist "build\Release\test_render.exe" (
    set "RENDER_EXE=build\Release\test_render.exe"
) else if exist "build\test_render.exe" (
    set "RENDER_EXE=build\test_render.exe"
) else if exist "build_v2\Release\test_render.exe" (
    set "RENDER_EXE=build_v2\Release\test_render.exe"
)

if "%RENDER_EXE%"=="" (
    echo  ┌──────────────────────────────────────────────────────────────┐
    echo  │  ⚠️  C++ rendering engine NOT compiled                      │
    echo  │                                                              │
    echo  │  The project will run in DEMO MODE:                         │
    echo  │  - You can VIEW pre-generated sample data                   │
    echo  │  - You CANNOT generate new synthetic data                   │
    echo  │  - To enable full functionality, compile the C++ engine:    │
    echo  │                                                              │
    echo  │    Requirements: Visual Studio 2019+ with C++ tools          │
    echo  │    Run: build_and_compile.bat                                │
    echo  │                                                              │
    echo  │  Or use Docker: docker build -t huhb3d .                    │
    echo  └──────────────────────────────────────────────────────────────┘
) else (
    echo  [OK] C++ engine found: %RENDER_EXE%
)

echo.
echo  [3/4] Checking demo data...
if exist "demo_data\rgb\frame_0001.png" (
    echo  [OK] Demo data available - you can preview sample results
) else (
    echo  [WARN] Demo data not found
)

echo.
echo  [4/4] Launching Huhb3D Web UI...
echo.
echo  ┌──────────────────────────────────────────────────────────────┐
echo  │  Starting Streamlit server...                                │
echo  │  Browser will open automatically at:                         │
echo  │                                                              │
echo  │    http://localhost:8501                                     │
echo  │                                                              │
echo  │  If browser does not open, manually visit the URL above.     │
echo  │                                                              │
echo  │  Press Ctrl+C to stop the server.                            │
echo  └──────────────────────────────────────────────────────────────┘
echo.

start "" "http://localhost:8501"

"%PYTHON%" -m streamlit run app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
