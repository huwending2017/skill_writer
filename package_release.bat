@echo off
setlocal
cd /d "%~dp0"

echo [release] Start packaging release zip
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0package_release.ps1"
if errorlevel 1 (
    echo [release] Failed.
    pause
    exit /b 1
)

echo [release] Done.
echo [release] Output dir: %~dp0release
pause
