@echo off
chcp 65001 >nul
python -m pip install -r requirements-host.txt
python -m pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --uac-admin --name MusicVMAutoHostDemo host_demo.py
REM GitHub Actions can build the same EXE automatically.
pause
