# Regenerate setup.bat / report.bat (ASCII + CRLF).
# Edit the $setup / $report strings below, then run:
#   powershell -ExecutionPolicy Bypass -File scripts\build-windows-bats.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

function Write-AsciiBat([string]$path, [string]$content) {
    $content = $content -replace "`r?`n", "`r`n"
    [System.IO.File]::WriteAllText((Join-Path $root $path), $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Wrote $path (UTF-8, CRLF)"
}

$setup = @'
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
'@

$report = @'
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Not installed yet. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Virtual environment is broken - likely copied from another PC.
    echo Delete the .venv folder, then run setup.bat again.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env not found. Run setup.bat and add API credentials.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
set "PY=.venv\Scripts\python.exe"

if "%~1"=="" (
    "%PY%" -u -m affiliate_report.gui.report_app
    exit /b !ERRORLEVEL!
)

if /I "%~1"=="update" (
    "%PY%" -u -m affiliate_report.updater
    set "RC=!ERRORLEVEL!"
    echo.
    pause
    exit /b !RC!
)

if "%~2"=="" (
    echo Usage: report.bat [YEAR MONTH [skip]] ^| update
    echo.
    echo Double-click report.bat to open the GUI.
    echo.
    echo Examples:
    echo   report.bat 2026 5          full run
    echo   report.bat 2026 5 skip     skip API fetch
    echo   report.bat update          update program from GitHub
    echo.
    pause
    exit /b 1
)

if not exist "data\reports" mkdir "data\reports"

for /f "delims=" %%M in ('"%PY%" -c "print(f'{int(%2):02d}')"') do set MM=%%M
set OUTPUT=data\reports\Affiliate_report_%1_!MM!.xlsx

set SKIP_ARG=
if /I "%~3"=="skip" set SKIP_ARG=--skip-fetch

echo ========================================
echo  Affiliate report for %1-%2
echo ========================================
echo.

affiliate-report report --year %1 --month %2 --output "!OUTPUT!" !SKIP_ARG!
if errorlevel 1 (
    echo.
    echo [ERROR] Report failed. Check .env credentials and network.
    pause
    exit /b 1
)

echo.
echo Done. Report saved:
echo   %CD%\!OUTPUT!
echo.
pause
'@

Write-AsciiBat "setup.bat" $setup
Write-AsciiBat "report.bat" $report
