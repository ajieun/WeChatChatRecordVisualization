@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo Drag exported CSV / JSON files (or a folder) onto this file to import.
  echo Or run:  python app\importer.py PATH
  pause
  exit /b 1
)
python app\importer.py %*
pause
