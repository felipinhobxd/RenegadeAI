@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_autoplay.ps1"
if errorlevel 1 (
  echo.
  echo RenegadeAI autoplay setup failed.
  pause
  exit /b 1
)
echo.
echo RenegadeAI autoplay is installed and running.
pause
