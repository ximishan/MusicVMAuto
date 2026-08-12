@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -m pip install -r requirements-host.txt
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name MusicVMAutoVisual host_visual.py

echo.
echo Build finished:
echo %CD%\dist\MusicVMAutoVisual.exe
pause
