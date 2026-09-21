@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "NOPAUSE="
if /i "%~1"=="/nopause" set "NOPAUSE=1"

if not exist "dist\DesktopMetrics\DesktopMetrics.exe" (
    echo Installed application files were not found.
    echo Run build_release.bat first.
    goto :error
)

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    where ISCC.exe >nul 2>nul
    if not errorlevel 1 set "ISCC=ISCC.exe"
)
if not defined ISCC goto :inno_missing

if not exist "release" mkdir "release"
echo Compiling Desktop Metrics installer with Inno Setup...
"%ISCC%" "installer\DesktopMetrics.iss"
if errorlevel 1 goto :error

if not defined NOPAUSE pause
exit /b 0

:inno_missing
echo.
echo Inno Setup 6 was not found. The portable EXE can still be used.
echo Install Inno Setup 6 and run build_installer.bat again.
if not defined NOPAUSE pause
exit /b 2

:error
if not defined NOPAUSE pause
exit /b 1
