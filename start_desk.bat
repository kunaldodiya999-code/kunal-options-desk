@echo off
rem Kunal Options Desk with REAL FYERS prices. Double-click me. Keep this window open while you use the desk.
cd /d "%~dp0"
title Kunal Options Desk
if not exist ".venv\Scripts\python.exe" (
  echo First time: setting up the desk. This takes a few minutes...
  call setup_desk.bat nopause
)
if not exist ".venv\Scripts\python.exe" goto fail
".venv\Scripts\python.exe" run.py %*
pause
exit /b
:fail
echo Setup did not finish. Please send Claude a screenshot of this window.
pause
