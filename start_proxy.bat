@echo off
setlocal
cd /d "%~dp0"
set CONFIG=config\profiles.local.json
if not exist "%CONFIG%" (
  copy config\profiles.example.json "%CONFIG%" >nul
  echo Created %CONFIG%. Edit upstream endpoints and enable the profiles you need.
  pause
  exit /b 0
)
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 run_proxy.py --config "%CONFIG%"
) else (
  python run_proxy.py --config "%CONFIG%"
)
endlocal
