@echo off
echo Building AgentGenerator for Windows...
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Install requirements
echo Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

:: Install PyInstaller
pip install pyinstaller
if errorlevel 1 (
    echo Failed to install PyInstaller.
    pause
    exit /b 1
)

:: Build
echo Building executable...
python build_exe.py

echo.
echo Build complete! Find AgentGenerator.exe in the dist/ folder.
pause
