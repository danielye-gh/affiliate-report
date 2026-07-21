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