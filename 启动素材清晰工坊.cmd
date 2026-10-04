@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "runtime\python.exe" (
  echo Missing portable runtime. Please extract all three ZIP files to the SAME folder.
  pause
  exit /b 1
)
"runtime\python.exe" "app.py"
if errorlevel 1 (
  echo.
  echo The app could not start. Please keep this window and send a screenshot for help.
  pause
)
endlocal
