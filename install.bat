@echo off
cd /d "%~dp0"
set SERVICE_NAME=CustomerPortraitService
set PORT=8099

echo.
echo === Customer Portrait Service - Install ===
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause & exit /b 1
)

:: Check config.yaml
if not exist "config.yaml" (
    echo [ERROR] config.yaml not found.
    pause & exit /b 1
)

:: Step 1: Create venv (always clean)
echo [1/3] Installing dependencies...
if exist ".venv" rmdir /s /q ".venv"
python -m venv .venv
if not exist ".venv\Scripts\pip.exe" (
    echo [ERROR] venv creation failed.
    pause & exit /b 1
)
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed.
    pause & exit /b 1
)
echo       Done.

:: Step 2: Find or download NSSM
echo [2/3] Setting up Windows service...
set NSSM=
if exist "C:\tools\nssm.exe"   set NSSM=C:\tools\nssm.exe
if exist "C:\nssm\nssm.exe"    set NSSM=C:\nssm\nssm.exe
if exist "%~dp0tools\nssm.exe" set NSSM=%~dp0tools\nssm.exe

if "%NSSM%"=="" (
    echo       NSSM not found. Downloading...
    if not exist "%~dp0tools" mkdir "%~dp0tools"
    powershell -NoProfile -Command "Invoke-WebRequest 'https://nssm.cc/release/nssm-2.24.zip' -OutFile '%~dp0tools\nssm.zip'; Expand-Archive '%~dp0tools\nssm.zip' '%~dp0tools\nssm_tmp' -Force; Copy-Item '%~dp0tools\nssm_tmp\nssm-2.24\win64\nssm.exe' '%~dp0tools\nssm.exe'"
    if exist "%~dp0tools\nssm.exe" (
        set NSSM=%~dp0tools\nssm.exe
    ) else (
        echo [ERROR] NSSM download failed.
        echo         Download nssm.exe from https://nssm.cc and put it in %~dp0tools\
        pause & exit /b 1
    )
)

:: Remove old service if exists
sc query %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    echo       Removing old service...
    "%NSSM%" stop %SERVICE_NAME% >nul 2>&1
    "%NSSM%" remove %SERVICE_NAME% confirm >nul 2>&1
)

:: Create log dir and register service
if not exist "%~dp0logs" mkdir "%~dp0logs"
set PYTHON=%~dp0.venv\Scripts\python.exe
set APPDIR=%~dp0

"%NSSM%" install %SERVICE_NAME% "%PYTHON%" server.py
"%NSSM%" set %SERVICE_NAME% AppDirectory "%APPDIR%"
"%NSSM%" set %SERVICE_NAME% DisplayName "Customer Portrait Service"
"%NSSM%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM%" set %SERVICE_NAME% AppStdout "%APPDIR%logs\service.log"
"%NSSM%" set %SERVICE_NAME% AppStderr "%APPDIR%logs\error.log"
"%NSSM%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM%" set %SERVICE_NAME% AppRotateBytes 5242880
echo       Service registered.

:: Step 3: Start and verify
echo [3/3] Starting service...
"%NSSM%" start %SERVICE_NAME%
timeout /t 5 /nobreak >nul

curl -s http://localhost:%PORT%/health >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo === Install complete ===
    echo Health: http://localhost:%PORT%/health
    echo Service: %SERVICE_NAME% (auto-start on boot)
) else (
    echo.
    echo [WARN] Service registered but not responding yet.
    echo        Check: http://localhost:%PORT%/health
    echo        Logs:  %~dp0logs\service.log
)

echo.
pause
