@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_VERSION=1.8.1"
set "LOG=%~dp0build_release.log"
set "FAIL_FILE=%~dp0release\BUILD_FAILED.txt"
set "PYTHON_EXE="
set "PYTHON_ARGS="
set "BUILD_EXE="
set "BUILD_ARGS="

if not exist "release" mkdir "release"
del /q "%FAIL_FILE%" >nul 2>nul
>"%LOG%" echo Desktop Metrics v%APP_VERSION% build log
>>"%LOG%" echo Started: %DATE% %TIME%
>>"%LOG%" echo Project: %CD%

echo Desktop Metrics v%APP_VERSION% release builder
echo.

rem A portable python.exe or its folder can be dragged onto this script.
if not "%~1"=="" (
    if exist "%~1\python.exe" (
        set "PYTHON_EXE=%~f1\python.exe"
    ) else if exist "%~1" (
        set "PYTHON_EXE=%~f1"
    )
)

rem Also support complete portable Python placed beside the project.
if not defined PYTHON_EXE if exist "%~dp0python\python.exe" set "PYTHON_EXE=%~dp0python\python.exe"
if not defined PYTHON_EXE if exist "%~dp0python311\python.exe" set "PYTHON_EXE=%~dp0python311\python.exe"
if not defined PYTHON_EXE if exist "%~dp0portable-python\python.exe" set "PYTHON_EXE=%~dp0portable-python\python.exe"

rem Finally, look for an installed 64-bit Python.
if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 (
        for %%V in (3.14 3.13 3.12 3.11 3.10) do (
            py -%%V -c "import sys, struct; raise SystemExit(0 if struct.calcsize('P') * 8 == 64 else 1)" >nul 2>nul
            if not errorlevel 1 if not defined PYTHON_EXE (
                set "PYTHON_EXE=py"
                set "PYTHON_ARGS=-%%V"
            )
        )
    )
)
if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE goto :python_missing

set PYRUN="%PYTHON_EXE%" %PYTHON_ARGS%

%PYRUN% -c "import sys, struct; print('Using Python:'); print(sys.executable); print(sys.version); raise SystemExit(0 if (3,10) <= sys.version_info[:2] < (3,15) and struct.calcsize('P') * 8 == 64 else 1)"
if errorlevel 1 goto :python_wrong

>>"%LOG%" echo.
>>"%LOG%" echo Python diagnostics:
%PYRUN% -c "import sys, struct; print('Executable:', sys.executable); print('Version:', sys.version); print('Bits:', struct.calcsize('P') * 8)" >>"%LOG%" 2>&1
%PYRUN% -c "import venv; print('venv: OK')" >>"%LOG%" 2>&1
%PYRUN% -m pip --version >>"%LOG%" 2>&1
%PYRUN% -m ensurepip --version >>"%LOG%" 2>&1

echo.
echo Validating release files...
%PYRUN% validate_release.py
if errorlevel 1 goto :validation_failed

rem Prefer an isolated build environment when venv is available.
%PYRUN% -c "import venv" >nul 2>nul
if errorlevel 1 goto :direct_build

if exist ".build-venv\Scripts\python.exe" (
    ".build-venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if errorlevel 1 rmdir /s /q ".build-venv"
)
if not exist ".build-venv\Scripts\python.exe" (
    echo Creating isolated build environment...
    %PYRUN% -m venv .build-venv
    if errorlevel 1 goto :direct_build
)
set "BUILD_EXE=%~dp0.build-venv\Scripts\python.exe"
set "BUILD_ARGS="
goto :install_build_tools

:direct_build
echo This Python does not provide a usable venv module. Trying direct pip build...
%PYRUN% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo pip is missing. Trying ensurepip...
    %PYRUN% -m ensurepip --upgrade
)
%PYRUN% -m pip --version >nul 2>nul
if errorlevel 1 goto :missing_components
set "BUILD_EXE=%PYTHON_EXE%"
set "BUILD_ARGS=%PYTHON_ARGS%"

:install_build_tools
set BUILDPY="%BUILD_EXE%" %BUILD_ARGS%
echo.
echo Installing/updating build tools. This requires internet access the first time...
%BUILDPY% -m pip install --upgrade pip
if errorlevel 1 goto :pip_failed
%BUILDPY% -m pip install -r requirements-build.txt
if errorlevel 1 goto :pip_failed

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
del /q "release\DesktopMetrics-Portable-v%APP_VERSION%.exe" >nul 2>nul
del /q "release\DesktopMetrics-Setup-v%APP_VERSION%.exe" >nul 2>nul

echo.
echo Building self-contained portable EXE...
%BUILDPY% -m PyInstaller --noconfirm --clean --windowed --onefile --noupx --optimize 1 ^
  --name DesktopMetrics-Portable ^
  --icon "%~dp0assets\desktop_metrics.ico" ^
  --version-file "%~dp0packaging\version_info_portable.txt" ^
  --add-data "%~dp0assets\desktop_metrics.ico;assets" ^
  --hidden-import pynvml ^
  --workpath "build\portable" ^
  --specpath "build\specs" ^
  --distpath "dist" ^
  "%~dp0portable_main.py"
if errorlevel 1 goto :pyinstaller_failed
copy /y "dist\DesktopMetrics-Portable.exe" "release\DesktopMetrics-Portable-v%APP_VERSION%.exe" >nul
if errorlevel 1 goto :copy_failed

echo.
echo Building the installed application folder...
%BUILDPY% -m PyInstaller --noconfirm --clean --windowed --onedir --noupx --optimize 1 ^
  --name DesktopMetrics ^
  --icon "%~dp0assets\desktop_metrics.ico" ^
  --version-file "%~dp0packaging\version_info_installed.txt" ^
  --add-data "%~dp0assets\desktop_metrics.ico;assets" ^
  --hidden-import pynvml ^
  --workpath "build\installed" ^
  --specpath "build\specs" ^
  --distpath "dist" ^
  "%~dp0main.py"
if errorlevel 1 goto :pyinstaller_failed

call "%~dp0build_installer.bat" /nopause
set "INSTALLER_RESULT=%ERRORLEVEL%"

echo.
echo Portable build complete:
echo   %~dp0release\DesktopMetrics-Portable-v%APP_VERSION%.exe
if "%INSTALLER_RESULT%"=="0" (
    echo Installer build complete:
    echo   %~dp0release\DesktopMetrics-Setup-v%APP_VERSION%.exe
) else (
    echo.
    echo Portable EXE built successfully. Installer was not compiled.
    echo Install Inno Setup 6 for the current user, then run build_installer.bat.
)
echo.
>>"%LOG%" echo Build completed successfully.
pause
exit /b 0

:python_missing
set "FAIL_REASON=No suitable Python was found. Drag a complete 64-bit Python 3.10-3.14 python.exe onto build_release.bat."
goto :failed_exit

:python_wrong
set "FAIL_REASON=The selected Python must be 64-bit Python 3.10 through 3.14."
goto :failed_exit

:validation_failed
set "FAIL_REASON=Release-file validation failed. See the console and build_release.log."
goto :failed_exit

:missing_components
set "FAIL_REASON=The selected Python has neither a usable venv nor working pip/ensurepip. Use a complete portable Python distribution with pip, or a normal Python installation."
goto :failed_exit

:pip_failed
set "FAIL_REASON=pip could not install the build dependencies. Check internet/proxy access and build_release.log."
goto :failed_exit

:pyinstaller_failed
set "FAIL_REASON=PyInstaller failed. Review the console output above."
goto :failed_exit

:copy_failed
set "FAIL_REASON=The EXE was built but could not be copied into the release folder. Check antivirus/permissions."
goto :failed_exit

:failed_exit
if not defined FAIL_REASON set "FAIL_REASON=Unknown build error."
>"%FAIL_FILE%" echo Desktop Metrics v%APP_VERSION% build failed.
>>"%FAIL_FILE%" echo.
>>"%FAIL_FILE%" echo %FAIL_REASON%
>>"%FAIL_FILE%" echo.
>>"%FAIL_FILE%" echo See build_release.log in the project folder for Python diagnostics.
>>"%LOG%" echo.
>>"%LOG%" echo FAILURE: %FAIL_REASON%
echo.
echo BUILD FAILED
echo %FAIL_REASON%
echo.
echo Failure note:
echo   %FAIL_FILE%
echo Diagnostics:
echo   %LOG%
echo.
pause
exit /b 1
