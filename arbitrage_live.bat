@echo off
rem Option arbitrage: live scanner during market hours. Double-click me. Keep this window open. No orders are placed.
cd /d "%~dp0"
title Option arbitrage - live scanner
if not exist ".venv\Scripts\python.exe" call setup_desk.bat nopause
".venv\Scripts\python.exe" arb_live.py %*
pause
