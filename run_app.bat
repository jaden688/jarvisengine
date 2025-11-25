@echo off
REM This batch file starts the Jarvis Engine application.

echo Locating Jarvis Engine...

REM Change directory to the location of this batch file.
cd /d "%~dp0"

echo Checking for required packages...
pip install -r requirements.txt
echo.

REM Set safety level to 'on' by default.
set "safety_level=on"
echo Starting application with safety level '%safety_level%'...
python main_app.py --safety %safety_level%
pause