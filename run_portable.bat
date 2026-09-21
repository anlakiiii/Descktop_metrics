@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        start "" ".venv\Scripts\pythonw.exe" main.py
        exit /b 0
    )
)

if not exist ".portable_python_path.txt" goto :not_configured
set /p "PY="<".portable_python_path.txt"
if not defined PY goto :not_configured
if not exist "%PY%" goto :python_missing

for %%I in ("%PY%") do set "PYDIR=%%~dpI"
set "PYW=%PYDIR%pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0main.py"
) else (
    start "" "%PY%" "%~dp0main.py"
)
exit /b 0

:not_configured
echo Portable Python has not been configured yet.
echo Drag your portable python.exe onto setup_portable.bat first.
pause
exit /b 1

:python_missing
echo The saved portable Python path no longer exists:
echo %PY%
echo Run setup_portable.bat again with the new python.exe location.
pause
exit /b 1
