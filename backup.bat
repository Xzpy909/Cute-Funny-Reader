@echo off
rem  Double-click to back up the reader's settings: accounts, reading progress, favourites, edits.
rem  The library files themselves (Data) are NOT copied - back those up separately.
cd /d "%~dp0"
title Backing up Cute^&Funny Reader
for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set TS=%%t
set DEST=backups\config-%TS%
echo.
echo   Backing up settings to %DEST% ...
robocopy config "%DEST%" /E /XD cache /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo   Backup FAILED - see above.
  pause
  exit /b 1
)
echo   Backup done: %DEST%
echo   (to restore: stop the reader, copy the files from there back into "config")
echo.
pause
