@echo off
rem TransformBro: build exe + NSIS installer + portable zip. ASCII only (CP866 safe).
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [X] No .venv found. Create it:
  echo     py -3.11 -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
  exit /b 1
)

tasklist /FI "IMAGENAME eq TransformBro.exe" 2>nul | find /i "TransformBro.exe" >nul
if not errorlevel 1 (
  echo [X] TransformBro.exe is running. Close it first.
  exit /b 1
)

echo [1/2] Building exe with PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm TransformBro.spec
if errorlevel 1 (
  echo [X] PyInstaller failed. See messages above.
  exit /b 1
)
if not exist "dist\TransformBro.exe" (
  echo [X] PyInstaller exited without error but dist\TransformBro.exe is missing.
  exit /b 1
)
copy /y "dist\TransformBro.exe" "TransformBro.exe" >nul
echo     exe copied to project root: TransformBro.exe

echo [2/2] Building installer and portable zip...
".venv\Scripts\python.exe" -X utf8 packaging\build_release.py --skip-build
if errorlevel 1 (
  echo [X] Release build failed.
  exit /b 1
)

echo.
echo Done. Files are in the "release" folder:
dir /b release
endlocal
