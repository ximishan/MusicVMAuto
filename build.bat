@echo off
chcp 65001 >nul
setlocal

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name MusicVMAutoDemo ^
  --collect-all pywinauto ^
  --collect-all pyautogui ^
  main.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\MusicVMAutoDemo.exe
pause
exit /b 0

:error
echo.
echo Build failed.
pause
exit /b 1
