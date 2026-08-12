@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -m pip install -r requirements-host.txt
python -m pip install pyinstaller
python -m py_compile host_controller.py
if errorlevel 1 exit /b 1
python -m py_compile host_controller_v054.py
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --collect-all rapidocr --name MusicVMAutoNoTemplate host_controller_v054.py

echo.
echo Build finished:
echo %CD%\dist\MusicVMAutoNoTemplate.exe
pause
