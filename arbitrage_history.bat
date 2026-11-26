@echo off
rem Option arbitrage: check the past year. Double-click me. Takes several hours (leave it running, e.g. overnight).
rem You can close the window any time: run me again and it carries on where it stopped.
cd /d "%~dp0"
title Option arbitrage - history check
if not exist ".venv\Scripts\python.exe" call setup_desk.bat nopause
".venv\Scripts\python.exe" arb_history.py %*
pause
