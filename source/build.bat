@echo off
setlocal
REM Build DualSenseCompanion.exe (self-contained, no Python needed to run it).
cd /d "%~dp0"

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)"
if errorlevel 1 (
  echo DS5Forge P0 build requires Python 3.12.x.
  python --version
  exit /b 1
)

python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

python -m PyInstaller build.spec --distpath dist --workpath build_tmp --noconfirm
if errorlevel 1 exit /b 1

echo.
echo Done. The executable is in dist\DualSenseCompanion.exe
endlocal
