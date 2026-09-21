@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    for %%V in (3.14 3.13 3.12 3.11 3.10) do (
        py -%%V -c "import sys, struct; raise SystemExit(0 if struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "PYTHON_CMD=py -%%V"
            goto :python_found
        )
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys, struct; raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
        goto :python_found
    )
)

goto :python_missing

:python_found
echo Using %PYTHON_CMD%
%PYTHON_CMD% --version

rem Prefer an isolated local environment when this Python contains venv.
%PYTHON_CMD% -c "import venv" >nul 2>nul
if errorlevel 1 goto :direct_mode

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 (
        echo Removing an unusable old .venv...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating a local Python environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :direct_mode
)

".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error
if exist ".direct_python_path.txt" del /q ".direct_python_path.txt" >nul 2>nul

start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:direct_mode
echo.
echo The selected Python does not provide a working venv module.
echo Dependencies will be installed directly into that Python installation.

%PYTHON_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo Trying to install pip with ensurepip...
    %PYTHON_CMD% -m ensurepip --upgrade
)
%PYTHON_CMD% -m pip --version >nul 2>nul
if errorlevel 1 goto :missing_components

%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 goto :error
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto :error
%PYTHON_CMD% -c "import sys; print(sys.executable)" > ".direct_python_path.txt"

%PYTHON_CMD% -c "import os,sys,subprocess; exe=os.path.join(os.path.dirname(sys.executable),'pythonw.exe'); exe=exe if os.path.exists(exe) else sys.executable; subprocess.Popen([exe,os.path.join(os.getcwd(),'main.py')],cwd=os.getcwd())"
if errorlevel 1 goto :error
exit /b 0

:python_missing
echo.
echo Desktop Metrics requires 64-bit Python 3.10 through 3.14.
echo Install Python from python.org or drag portable python.exe onto setup_portable.bat.
pause
exit /b 1

:missing_components
echo.
echo This Python has neither venv nor a working pip/ensurepip module.
echo Repair the full Python installation, use a complete portable Python,
echo or run a standalone DesktopMetrics.exe built on another Windows PC.
pause
exit /b 1

:error
echo.
echo Desktop Metrics setup failed. Review the messages above.
pause
exit /b 1
