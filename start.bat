@echo off
setlocal
cd /d "%~dp0"
set PYTHON_CMD=
where py >nul 2>nul
if %errorlevel%==0 set PYTHON_CMD=py -3
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if %errorlevel%==0 set PYTHON_CMD=python
)
if not defined PYTHON_CMD (
  echo Python 3.10+ was not found.
  echo Use an IT-approved portable Python runtime and add it to PATH.
  pause
  exit /b 1
)
%PYTHON_CMD% -c "import flask" >nul 2>nul
if errorlevel 1 (
  echo Flask is missing. Install it in your permitted user environment:
  echo %PYTHON_CMD% -m pip install --user -r requirements.txt
  echo If package installation is blocked by office policy, request IT approval.
  pause
  exit /b 1
)
start "POS Network Simulator" http://127.0.0.1:5050
%PYTHON_CMD% app.py
endlocal
