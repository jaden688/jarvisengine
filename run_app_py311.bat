@echo off
title JL Engine (Python 3.11)

REM Run from the directory this script lives in
cd /d "%~dp0"

set OLLAMA_URL=http://127.0.0.1:11434

echo Checking Ollama at %OLLAMA_URL% ...
powershell -NoLogo -NoProfile -Command ^
  "try { (Invoke-WebRequest -UseBasicParsing '%OLLAMA_URL%/api/tags' -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
if not errorlevel 1 (
  echo Ollama already running.
) else (
  echo Starting Ollama server...
  start "Ollama Serve" /min cmd /c "ollama serve"
  timeout /t 2 >nul
)

echo Starting JL Engine with Python 3.11...
py -3.11 main_app.py
