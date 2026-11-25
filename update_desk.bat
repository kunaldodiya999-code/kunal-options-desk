@echo off
rem Kunal Options Desk - download Claude's latest changes from GitHub, then set up again. Double-click me.
rem It runs from a temporary copy, because downloading may replace this very file.
if /i not "%~1"=="_run" (
  copy /y "%~f0" "%TEMP%\kod_update.bat" >nul
  "%TEMP%\kod_update.bat" _run "%~dp0"
  exit /b
)
cd /d "%~2"
title Kunal Options Desk - update
where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed on this PC. Install it from git-scm.com, then try again.
  goto end
)
if not exist ".git" (
  echo This folder was not downloaded with git, so it is being connected to GitHub now...
  git init -q
  git remote add origin https://github.com/kunaldodiya999-code/kunal-options-desk
)
echo Downloading the latest version from GitHub...
git -c http.version=HTTP/1.1 fetch origin main
if errorlevel 1 (
  echo.
  echo The download did not work. Please send Claude a screenshot of this window.
  goto end
)
git checkout -q -f -B main origin/main
if errorlevel 1 (
  echo.
  echo Could not switch to the new version. Please send Claude a screenshot of this window.
  goto end
)
echo.
echo Now on this version:
git log -1 --format="  %%h  %%cd  %%s" --date=format:"%%d %%b %%Y %%H:%%M"
echo.
call setup_desk.bat nopause
:end
pause
