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

if exist ".direct_python_path.txt" (
    set /p "PY="<".direct_python_path.txt"
    if defined PY if exist "%PY%" (
        for %%I in ("%PY%") do set "PYDIR=%%~dpI"
        if exist "%PYDIR%pythonw.exe" (
            start "" "%PYDIR%pythonw.exe" "%~dp0main.py"
        ) else (
            start "" "%PY%" "%~dp0main.py"
        )
        exit /b 0
    )
)

call setup_and_run.bat
exit /b %errorlevel%
