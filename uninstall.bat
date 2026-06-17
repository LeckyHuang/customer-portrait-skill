@echo off
cd /d "%~dp0"
set SERVICE_NAME=CustomerPortraitService

set NSSM=
if exist "C:\tools\nssm.exe"   set NSSM=C:\tools\nssm.exe
if exist "C:\nssm\nssm.exe"    set NSSM=C:\nssm\nssm.exe
if exist "%~dp0tools\nssm.exe" set NSSM=%~dp0tools\nssm.exe

if "%NSSM%"=="" (
    echo [ERROR] NSSM not found. Please manually remove service: %SERVICE_NAME%
    pause & exit /b 1
)

echo Stopping and removing service %SERVICE_NAME% ...
"%NSSM%" stop %SERVICE_NAME% >nul 2>&1
"%NSSM%" remove %SERVICE_NAME% confirm
echo Done.
pause
