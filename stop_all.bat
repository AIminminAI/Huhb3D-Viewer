@echo off
chcp 65001 > nul
title Huhb3D Stop All Services

echo ============================================
echo   Huhb3D Viewer - Stop All Services
echo ============================================
echo.

echo Stopping Streamlit processes (app.py / agent_ui.py) ...
taskkill /f /fi "WINDOWTITLE eq Huhb3D-DataGenerator*" > nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Huhb3D-AIAgent*" > nul 2>&1

echo Stopping Node.js server ...
taskkill /f /fi "WINDOWTITLE eq Huhb3D-NodeServer*" > nul 2>&1

for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8501 .*LISTENING"') do (
    taskkill /f /pid %%a > nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8502 .*LISTENING"') do (
    taskkill /f /pid %%a > nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8080 .*LISTENING"') do (
    taskkill /f /pid %%a > nul 2>&1
)

echo.
echo All services stopped.
timeout /t 2 /nobreak > nul
