@echo off
REM Build DualSenseCompanion.exe (self-contained, no Python needed to run it).
cd /d "%~dp0"
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller build.spec --distpath dist --workpath build_tmp --noconfirm
echo.
echo Done. The executable is in dist\DualSenseCompanion.exe
pause
