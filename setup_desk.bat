@echo off
rem Kunal Options Desk - setup. Double-click me (safe to run again any time).
cd /d "%~dp0"
title Kunal Options Desk - setup
set "PYEXE="
where py >nul 2>nul && set "PYEXE=py -3"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE (
  echo Python was not found on this PC. Install it from python.org, tick "Add python.exe to PATH", then try again.
  set RC=1
  goto end
)
%PYEXE% setup_pc.py
set RC=%errorlevel%
:end
if /i not "%~1"=="nopause" pause
exit /b %RC%
