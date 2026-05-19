@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clean_workspace.ps1" %*
if errorlevel 1 (
  echo.
  echo [clean] failed
  exit /b 1
)
echo.
echo [clean] done
