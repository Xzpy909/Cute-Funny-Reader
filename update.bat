@echo off
rem  Double-click to rebuild the reader with the latest changes and open it.
cd /d "%~dp0"
title Updating Cute^&Funny Reader
echo.
echo   Rebuilding Cute^&Funny Reader... (this can take a minute)
echo.
docker compose up -d --build
if errorlevel 1 (
  echo.
  echo   Something went wrong - see the messages above.
  echo   Is Docker Desktop running?
  echo.
  pause
  exit /b 1
)
echo.
echo   Done - opening the reader. Already-open tabs will offer a Reload button.
start "" http://localhost:9001
timeout /t 4 >nul
