@echo off
rem  Double-click to start the reader in dev mode: it runs the code straight from the app folder,
rem  so new changes show up after a browser refresh (no rebuild). update.bat goes back to normal mode.
cd /d "%~dp0"
title Cute^&Funny Reader - dev mode
echo.
echo   Starting Cute^&Funny Reader in dev mode...
echo.
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
if errorlevel 1 (
  echo.
  echo   Something went wrong - see the messages above.
  echo   Is Docker Desktop running?
  echo.
  pause
  exit /b 1
)
echo.
echo   Done - dev mode is on. From now on a browser refresh is enough after a change.
start "" http://localhost:9001
timeout /t 4 >nul
