@echo off
TITLE PiSelfhosting Configurator

REM This script starts the Flask web application for the PiSelfhosting configurator.
REM It ensures the Python virtual environment is activated first.

echo Activating Python virtual environment...
call "%~dp0.venv\Scripts\activate.bat"

REM Check if the virtual environment was activated successfully
if errorlevel 1 (
    echo.
    echo ERROR: Could not activate the virtual environment.
    echo Please ensure you have run the setup steps in CONTRIBUTING.md.
    pause
    exit /b
)

echo.
echo Starting the Configurator web application...
echo You can close this window by pressing CTRL+C in the terminal.
echo.

python "%~dp0configurator_app\app.py"

echo.
echo Application has finished.
pause