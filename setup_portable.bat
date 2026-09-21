@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="

rem You can drag python.exe (or its folder) onto this batch file.
if not "%~1"=="" (
    if exist "%~1\python.exe" (
        set "PY=%~f1\python.exe"
    ) else if exist "%~1" (
        set "PY=%~f1"
    )
)

rem Or place portable Python in one of these folders beside this script.
if not defined PY if exist "%~dp0python\python.exe" set "PY=%~dp0python\python.exe"
if not defined PY if exist "%~dp0python311\python.exe" set "PY=%~dp0python311\python.exe"
if not defined PY if exist "%~dp0portable-python\python.exe" set "PY=%~dp0portable-python\python.exe"

if not defined PY goto :usage
if not exist "%PY%" goto :usage

"%PY%" -c "import sys, struct; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Desktop Metrics requires 64-bit Python 3.10 through 3.14.
    echo Selected interpreter: %PY%
    pause
    exit /b 1
)

>".portable_python_path.txt" echo(%PY%

echo Using: %PY%
"%PY%" --version

rem Preferred mode: create an isolated local virtual environment.
"%PY%" -c "import venv" >nul 2>nul
if not errorlevel 1 goto :venv_mode

rem Some complete portable distributions have pip but omit venv.
rem In that case, install into the portable interpreter itself.
for %%I in ("%PY%") do set "PYDIR=%%~dpI"
for %%F in ("%PYDIR%python*._pth") do if exist "%%~fF" goto :embedded_unsupported

"%PY%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo venv is unavailable. Trying to add pip...
    "%PY%" -m ensurepip --upgrade
)

"%PY%" -m pip --version >nul 2>nul
if errorlevel 1 goto :missing_components

echo.
echo venv is unavailable, so dependencies will be installed directly
echo into this portable Python folder.
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :error

goto :launch_portable

:venv_mode
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo Removing an unusable old .venv...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Creating the local .venv environment...
    "%PY%" -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:launch_portable
set "PYW=%PYDIR%pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0main.py"
) else (
    start "" "%PY%" "%~dp0main.py"
)
exit /b 0

:embedded_unsupported
echo.
echo This appears to be Python's minimal embeddable ZIP package.
echo That package normally has no venv or supported pip environment.
echo Use a complete portable distribution with pip/venv, install full Python,
echo or build DesktopMetrics.exe on another Windows PC and copy the EXE here.
pause
exit /b 1

:missing_components
echo.
echo This portable Python has neither venv nor a working pip/ensurepip module.
echo Use a complete portable Python distribution or the full python.org installer.
pause
exit /b 1

:usage
echo.
echo Portable Python was not found.
echo.
echo Easiest method:
echo   1. Copy this file into the extracted DesktopMetrics folder.
echo   2. Drag your portable python.exe onto setup_portable.bat.
echo.
echo Alternative: put portable Python in one of these folders:
echo   %~dp0python\python.exe
echo   %~dp0python311\python.exe
echo   %~dp0portable-python\python.exe
echo.
pause
exit /b 1

:error
echo.
echo Desktop Metrics setup failed. Review the error shown above.
pause
exit /b 1
