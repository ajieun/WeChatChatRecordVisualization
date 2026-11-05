@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo  重新从微信数据库导出最新聊天记录（需微信已登录）
echo  说明：会先重新取密钥，再全量重建 data\archive.db
echo ================================================
echo.
".venv\Scripts\python.exe" "scripts\export_to_archive.py"
if errorlevel 1 (
  echo.
  echo [X] 导出失败，请确认微信已登录且本窗口有足够权限
) else (
  echo.
  echo [OK] 完成，重新打开查看器即可看到最新数据
)
pause
