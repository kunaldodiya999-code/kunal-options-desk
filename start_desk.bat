@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo First run setup:  python setup_pc.py
  pause
  exit /b 1
)
.venv\Scripts\python.exe run.py %*
pause
