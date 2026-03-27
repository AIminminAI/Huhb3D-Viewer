@echo off
chcp 65001 > nul

echo Starting script...

rem Environment variable isolation
setlocal

rem Initialize Visual Studio environment
echo Initializing VS environment...
call "D:\Huhb\SoftwareSetUp\Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
if errorlevel 1 (
    echo Environment initialization failed!
    exit /b 1
)

echo Environment initialized successfully.

rem Check if GLFW source exists locally
echo Checking for local GLFW source...
if exist "build\_deps\glfw-src" (
    echo Local GLFW source found, preserving it...
    rem Create a temporary directory to save GLFW source
    if not exist "glfw_temp" mkdir glfw_temp
    xcopy /s /e /i "build\_deps\glfw-src" "glfw_temp"
)

rem Clean old build folder
echo Cleaning old build folder...
if exist build rmdir /s /q build

rem Restore GLFW source if it was preserved
if exist "glfw_temp" (
    echo Restoring GLFW source...
    mkdir build
    mkdir build\_deps
    xcopy /s /e /i "glfw_temp" "build\_deps\glfw-src"
    rmdir /s /q glfw_temp
)

rem Create build folder
echo Creating build folder...
mkdir build

rem Run cmake configuration with NMake generator
echo Running cmake configuration with NMake Makefiles...
echo Note: If download fails due to network issues, please manually download GLFW source code.
echo Suggested: Download GLFW 3.3.8 from https://github.com/glfw/glfw/releases/tag/3.3.8
echo and place it in build/_deps/glfw-src
cmake -B build -S . -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 (
    echo CMake configuration failed!
    echo Please check your network connection or manually download GLFW source code.
    goto :error
)

rem GLAD is now provided by GLFW library, no need to check glad_gl.c


rem Build project
echo Building project...
cmake --build build
if errorlevel 1 (
    echo Build failed!
    goto :error
)

rem Check if STL file exists
if not exist "Dji+Avata+2+Simple.stl" (
    echo MODEL MISSING!
    goto :error
)

rem Check where the executable is located
set "EXE_PATH=build"
echo Using build folder as executable path.

rem Copy STL file to executable folder
echo Copying STL file...
copy /Y "Dji+Avata+2+Simple.stl" "%EXE_PATH%" > nul
if errorlevel 1 (
    echo Failed to copy STL file!
    pause
    goto :error
)

rem Copy necessary DLL files
echo Copying necessary DLL files...

rem Find Python DLL using WHERE command
echo Finding Python DLL...
set "PYTHON_DLL="
for /f "tokens=*" %%i in ('where python312.dll 2^>nul') do set "PYTHON_DLL=%%i"

if "%PYTHON_DLL%"=="" (
    for /f "tokens=*" %%i in ('where python3.dll 2^>nul') do set "PYTHON_DLL=%%i"
)

if "%PYTHON_DLL%"=="" (
    rem Try common Python installation paths
    if exist "C:\ProgramData\miniconda3\python312.dll" set "PYTHON_DLL=C:\ProgramData\miniconda3\python312.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\anaconda3\python312.dll" set "PYTHON_DLL=C:\ProgramData\anaconda3\python312.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\miniconda3\Library\bin\python312.dll" set "PYTHON_DLL=C:\ProgramData\miniconda3\Library\bin\python312.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\anaconda3\Library\bin\python312.dll" set "PYTHON_DLL=C:\ProgramData\anaconda3\Library\bin\python312.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\miniconda3\python3.dll" set "PYTHON_DLL=C:\ProgramData\miniconda3\python3.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\anaconda3\python3.dll" set "PYTHON_DLL=C:\ProgramData\anaconda3\python3.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\miniconda3\Library\bin\python3.dll" set "PYTHON_DLL=C:\ProgramData\miniconda3\Library\bin\python3.dll"
    if "%PYTHON_DLL%"=="" if exist "C:\ProgramData\anaconda3\Library\bin\python3.dll" set "PYTHON_DLL=C:\ProgramData\anaconda3\Library\bin\python3.dll"
)

if not "%PYTHON_DLL%"=="" (
    echo Found Python DLL: %PYTHON_DLL%
    copy /Y "%PYTHON_DLL%" "%EXE_PATH%" > nul
    if errorlevel 1 (
        echo Failed to copy Python DLL!
        goto :error
    )
    echo Python DLL copied successfully.
    
    rem Add Python directories to PATH
    for %%i in ("%PYTHON_DLL%") do set "PYTHON_DIR=%%~dpi"
    echo Adding Python directory to PATH: %PYTHON_DIR%
    set "PATH=%PATH%;%PYTHON_DIR%"
    
    rem Also add Library\bin to PATH
    set "PYTHON_LIBRARY_BIN=%PYTHON_DIR:bin=Library\bin%"
    if exist "%PYTHON_LIBRARY_BIN%" (
        echo Adding Python Library\bin to PATH: %PYTHON_LIBRARY_BIN%
        set "PATH=%PATH%;%PYTHON_LIBRARY_BIN%"
    )
) else (
    echo WARNING: Python DLL not found!
    rem Try adding common Python paths to PATH
    set "PATH=%PATH%;C:\ProgramData\miniconda3;C:\ProgramData\anaconda3;C:\ProgramData\miniconda3\Library\bin;C:\ProgramData\anaconda3\Library\bin"
)

rem Find and copy vcruntime140.dll
echo Finding vcruntime140.dll...
set "VCRUNTIME_DLL="
for /f "tokens=*" %%i in ('where vcruntime140.dll 2^>nul') do set "VCRUNTIME_DLL=%%i"

if not "%VCRUNTIME_DLL%"=="" (
    echo Found vcruntime140.dll: %VCRUNTIME_DLL%
    copy /Y "%VCRUNTIME_DLL%" "%EXE_PATH%" > nul
    if errorlevel 1 (
        echo Failed to copy vcruntime140.dll!
        goto :error
    )
    echo vcruntime140.dll copied successfully.
) else (
    echo WARNING: vcruntime140.dll not found!
)

rem Find and copy msvcp140.dll
echo Finding msvcp140.dll...
set "MSVCP_DLL="
for /f "tokens=*" %%i in ('where msvcp140.dll 2^>nul') do set "MSVCP_DLL=%%i"

if not "%MSVCP_DLL%"=="" (
    echo Found msvcp140.dll: %MSVCP_DLL%
    copy /Y "%MSVCP_DLL%" "%EXE_PATH%" > nul
    if errorlevel 1 (
        echo Failed to copy msvcp140.dll!
        goto :error
    )
    echo msvcp140.dll copied successfully.
) else (
    echo WARNING: msvcp140.dll not found!
)

rem Search for GLFW DLL in entire build folder
echo Searching for GLFW DLL in build folder...
set "GLFW_DLL_FOUND=0"
for /r build %%f in (glfw3.dll) do (
    echo Found GLFW DLL: %%f
    copy /y "%%f" "%EXE_PATH%" > nul
    if errorlevel 1 (
        echo WARNING: Failed to copy GLFW DLL, but continuing anyway.
    ) else (
        echo GLFW DLL copied successfully.
    )
    set "GLFW_DLL_FOUND=1"
    goto :glfw_done
)
:glfw_done
if "%GLFW_DLL_FOUND%"=="0" (
    echo WARNING: GLFW DLL not found in build folder!
    echo Note: GLFW should be statically linked, so this might not be a problem.
)

rem Run program
echo Running program...

rem Set PYTHONHOME environment variable
echo Setting PYTHONHOME environment variable...
if exist "C:\ProgramData\miniconda3" (
    set "PYTHONHOME=C:\ProgramData\miniconda3"
    echo PYTHONHOME set to: C:\ProgramData\miniconda3
    rem Add Python Lib to PYTHONPATH
    if exist "C:\ProgramData\miniconda3\Lib" (
        set "PYTHONPATH=%PYTHONPATH%;C:\ProgramData\miniconda3\Lib"
        echo Added Python Lib to PYTHONPATH
    )
) else if exist "C:\ProgramData\anaconda3" (
    set "PYTHONHOME=C:\ProgramData\anaconda3"
    echo PYTHONHOME set to: C:\ProgramData\anaconda3
    rem Add Python Lib to PYTHONPATH
    if exist "C:\ProgramData\anaconda3\Lib" (
        set "PYTHONPATH=%PYTHONPATH%;C:\ProgramData\anaconda3\Lib"
        echo Added Python Lib to PYTHONPATH
    )
) else (
    echo WARNING: PYTHONHOME not set!
)

echo Listing files in execution directory:
cd "%EXE_PATH%"
dir /b
echo Build completed successfully!

rem Check if test_render.exe exists and run it if available
if exist "test_render.exe" (
    echo Starting test_render.exe with error logging...
    test_render.exe > log.txt 2>&1
    if errorlevel 1 (
        echo Program execution failed!
        echo Displaying error log:
        type log.txt
        pause
        goto :error
    ) else (
        echo Program executed successfully!
        del log.txt > nul 2>&1
    )
) else (
    echo test_render.exe not found (render module is disabled).
    echo Core modules built successfully!
)

echo Program execution completed!
pause
exit /b 0

:error
echo Error occurred!
pause
exit /b 1