@echo off
rem Backward-compatible launcher. Drag portable python.exe onto this file, or
rem double-click it when a normal Python installation is available.
call "%~dp0build_release.bat" %*
exit /b %ERRORLEVEL%
