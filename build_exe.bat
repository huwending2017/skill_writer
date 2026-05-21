@echo off
setlocal
cd /d "%~dp0"

echo [build] Start building SkillWriterDesktop portable exe and folder build
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_exe.ps1"
if errorlevel 1 (
    echo [build] Failed.
    pause
    exit /b 1
)

echo [build] Done.
echo [build] Portable EXE: %~dp0dist\SkillWriterDesktopPortable.exe
echo [build] Folder build: %~dp0dist\SkillWriterDesktop\start_skill_writer_desktop.bat
echo [build] Note: do not copy dist\SkillWriterDesktop\SkillWriterDesktop.exe alone.
pause
