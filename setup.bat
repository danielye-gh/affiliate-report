@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  Affiliate Report - Windows Setup
echo ========================================
echo.

set "PY=py"
py --version >nul 2>&1
if errorlevel 1 (
    set "PY=python"
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python not found.
        echo Install Python 3.9+ from https://www.python.org/downloads/
        echo Check "Add python.exe to PATH", or use the Windows "py" launcher.
        echo.
        pause
        exit /b 1
    )
)

echo [1/3] Creating virtual environment .venv ...
set "NEED_VENV=1"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 set "NEED_VENV=0"
)
if "%NEED_VENV%"=="0" (
    echo       Already exists, skipping.
) else (
    if exist ".venv" (
        echo       Broken or copied .venv detected - recreating ...
        rmdir /s /q ".venv"
    )
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/3] Installing dependencies ...
call .venv\Scripts\activate.bat
set "PIP=.venv\Scripts\python.exe -m pip"
set "MIRROR=-i https://pypi.tuna.tsinghua.edu.cn/simple"

echo       Upgrading pip/setuptools ...
%PIP% install --upgrade pip setuptools wheel %MIRROR% >nul 2>&1
if errorlevel 1 (
    %PIP% install --upgrade pip setuptools wheel >nul 2>&1
)

echo       Using Tsinghua PyPI mirror ...
%PIP% install -e . %MIRROR%
if errorlevel 1 (
    echo       Mirror failed, trying official PyPI ...
    %PIP% install -e .
    if errorlevel 1 (
        echo [ERROR] Install failed. Check network or proxy settings.
        pause
        exit /b 1
    )
)

echo [3/3] Checking config ...
if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo       Copied .env.example to .env - edit .env with API credentials.
    ) else (
        echo       .env not found - contact admin for credentials.
    )
) else (
    echo       .env already exists.
)

if not exist "data\reports" mkdir "data\reports"

echo.
echo Setup complete.
echo Next: edit .env, then run   report.bat YEAR MONTH
echo Example:                    report.bat 2026 5
echo.
pause