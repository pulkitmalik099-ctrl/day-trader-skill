@echo off
setlocal
cd /d "%~dp0"
title Day Trader Skill Hub
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.8+ was not found. Opening the download page...
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% server.py
if errorlevel 1 pause
