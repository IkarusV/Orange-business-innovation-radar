@echo off
setlocal
cd /d "%~dp0"
title Orange Business Innovation Radar V2
echo.
echo Starting Orange Business Innovation Radar V2...
echo Working directory: %CD%
echo Frontend: http://localhost:3030
echo.
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  where py >nul 2>nul
  if not errorlevel 1 (py -3 -m venv ".venv") else (python -m venv ".venv")
  if errorlevel 1 goto :error
)
echo Installing or checking dependencies...
".venv\Scripts\python.exe" -m pip install -r "requirements.txt"
if errorlevel 1 goto :error
echo.
echo Starting Reflex. Keep this window open while using the radar.
echo Open http://localhost:3030 in your browser.
echo.
".venv\Scripts\python.exe" -m reflex run
if errorlevel 1 goto :error
goto :eof

:error
echo.
echo The radar could not start. The error above explains the problem.
echo Check that Python 3.11+ and Node.js are installed and that ports 3030 and 8031 are free.
echo.
pause
exit /b 1
