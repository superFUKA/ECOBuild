@echo off
rem ECOBuild installer (Windows). Double-click to run. Options are passed to install.ps1 (e.g. -Ref main).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set code=%errorlevel%
echo.
pause
exit /b %code%
