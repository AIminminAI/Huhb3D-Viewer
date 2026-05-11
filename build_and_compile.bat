@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

title Huhb3D - Build C++ Rendering Engine

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║     Huhb3D - C++ Rendering Engine Builder                   ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo  [1/3] Detecting Visual Studio...

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VS_PATH="

if exist "%VSWHERE%" (
    for /f "tokens=*" %%i in ('"%VSWHERE%" -latest -property installationPath 2^> nul') do set "VS_PATH=%%i"
)

if not defined VS_PATH (
    if exist "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" (
        set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Community"
    )
    if exist "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat" (
        set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Professional"
    )
    if exist "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat" (
        set "VS_PATH=C:\Program Files\Microsoft Visual Studio\2022\Enterprise"
    )
    if exist "C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Auxiliary\Build\vcvarsall.bat" (
        set "VS_PATH=C:\Program Files (x86)\Microsoft Visual Studio\2019\Community"
    )
)

if not defined VS_PATH (
    echo  [ERROR] Visual Studio not found!
    echo  Please install Visual Studio 2019 or 2022 with "Desktop development with C++" workload
    echo  Download: https://visualstudio.microsoft.com/downloads/
    pause
    exit /b 1
)

echo  [OK] Visual Studio: %VS_PATH%

set "VCVARS=%VS_PATH%\VC\Auxiliary\Build\vcvarsall.bat"
if not exist "%VCVARS%" (
    echo  [ERROR] vcvarsall.bat not found at: %VCVARS%
    pause
    exit /b 1
)

echo.
echo  [2/3] Setting up build environment...
call "%VCVARS%" x64
if errorlevel 1 (
    echo  [ERROR] Failed to initialize Visual Studio environment
    pause
    exit /b 1
)

echo.
echo  [3/3] Building C++ rendering engine...

if exist build rmdir /s /q build
mkdir build
cd build

cmake -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release ..
if errorlevel 1 (
    echo.
    echo  [INFO] NMake failed, trying default generator...
    cd ..
    rmdir /s /q build
    mkdir build
    cd build
    cmake -DCMAKE_BUILD_TYPE=Release ..
    if errorlevel 1 (
        echo  [ERROR] CMake configure failed!
        echo  Make sure you have CMake installed: https://cmake.org/download/
        pause
        exit /b 1
    )
    cmake --build . --config Release
) else (
    cmake --build . 2>&1
)

if errorlevel 1 (
    echo.
    echo  [ERROR] Build failed!
    echo  Common issues:
    echo  - Missing GLFW: check deps/ folder contains glfw library
    echo  - Missing OpenGL: ensure GPU drivers are up to date
    echo  - Missing C++ tools: install "Desktop development with C++" in VS Installer
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║  ✅ Build successful!                                        ║
echo  ║                                                              ║
echo  ║  Now run start_demo.bat to launch the application.           ║
echo  ╚══════════════════════════════════════════════════════════════╝
pause
