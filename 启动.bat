@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Python not found. Please install Python 3.10+ and add it to PATH.
  pause
  exit /b 1
)
echo Starting local chat viewer...
python app\server.py
pause
