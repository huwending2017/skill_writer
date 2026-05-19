@echo off
setlocal
cd /d "%~dp0"

echo [build] Start building SkillWriterDesktop.exe
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"
if errorlevel 1 (
    echo [build] Failed.
    pause
    exit /b 1
)

echo [build] Done.
echo [build] EXE: %~dp0dist\SkillWriterDesktop\SkillWriterDesktop.exe
pause
