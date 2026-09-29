@echo off
cd /d "%~dp0"
python switch_model.py --set 14b --no-test
python launch.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Error] Launch failed.
)
pause
