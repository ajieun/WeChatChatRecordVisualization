@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo  安装依赖（首次使用运行一次）
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [X] 没找到 python，请先安装 Python 3.10+ 并勾选 "Add to PATH"
  pause
  exit /b 1
)

if not exist ".venv" (
  echo [1/3] 创建虚拟环境...
  python -m venv .venv
  if errorlevel 1 ( echo [X] 创建虚拟环境失败 & pause & exit /b 1 )
)

echo [2/3] 安装 wechatauto-replica（--no-deps，避免重依赖）...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
if not exist "_tools\pkg" mkdir "_tools\pkg"
".venv\Scripts\python.exe" -m pip download -q --no-deps -d "_tools\pkg" wechatauto-replica
".venv\Scripts\python.exe" -m pip install -q --no-deps "_tools\pkg\wechatauto_replica-*.whl"
if errorlevel 1 ( echo [X] 安装失败，请检查网络 & pause & exit /b 1 )

echo [3/3] 安装运行依赖...
".venv\Scripts\python.exe" -m pip install -q cryptography zstandard pywin32 colorama

if not exist "config.py" (
  copy "config.example.py" "config.py" >nul
  echo.
  echo [!] 已生成 config.py，请打开它填写 DB_DIR 和 ACCOUNT 后再继续
)

echo.
echo [OK] 依赖安装完成
pause
