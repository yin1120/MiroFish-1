@echo off
cd /d "%~dp0"
python test_grok.py --launch
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Error] Launch failed.
)
pause
