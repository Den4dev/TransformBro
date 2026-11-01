@echo off
rem TransformBro build script (ASCII-only to avoid CP866/CP1251 issues)
cd /d "%~dp0"
tasklist /FI "IMAGENAME eq TransformBro.exe" | find /i "TransformBro.exe" >nul
if not errorlevel 1 (
    echo Close running TransformBro.exe first!
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm TransformBro.spec
if errorlevel 1 (
    echo BUILD FAILED - see build\ logs
    pause
    exit /b 1
)
copy /y dist\TransformBro.exe TransformBro.exe >nul
echo OK - TransformBro.exe updated in project root.
pause
