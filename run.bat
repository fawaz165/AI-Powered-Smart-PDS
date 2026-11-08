@echo off
title AI-Powered Smart PDS Server
cd /d "%~dp0"

echo ===================================================
echo Starting AI-Powered Smart Public Distribution System
echo ===================================================
echo.

:: 1. Activate Virtual Environment if available
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment (.venv)...
    call .venv\Scripts\activate.bat
) else if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment (venv)...
    call venv\Scripts\activate.bat
)

:: 2. Check if Python is available
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)

:: 3. Check if MongoDB is reachable on port 27017
echo [INFO] Checking MongoDB connection on port 27017...
powershell -Command "$c=New-Object System.Net.Sockets.TcpClient; try{ $c.Connect('127.0.0.1', 27017); $c.Close(); exit 0 }catch{ exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] MongoDB is not responding on 127.0.0.1:27017.
    echo Attempting to start MongoDB container via Docker...
    where docker >nul 2>&1
    if not errorlevel 1 (
        docker start smart_pds_mongo >nul 2>&1
        timeout /t 2 >nul
    )
)

echo.
echo ===================================================
echo  Access URL:  http://localhost:5000
echo.
echo  Default Accounts:
echo   - Administrator:     admin / admin123
echo   - District Officer:  officer_chennai / officer123
echo   - FPS Dealer:        dealer_001 / dealer123
echo ===================================================
echo.
echo Waiting for server to be ready before opening browser...

:: 4. Background job: wait until port 5000 is open, then launch browser
start "" powershell -WindowStyle Hidden -Command "$ready=$false; for($i=0; $i -lt 30 -and -not $ready; $i++){ try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5000); $c.Close(); $ready=$true } catch { Start-Sleep -Milliseconds 500 } }; if($ready){ Start-Process 'http://localhost:5000' }"

:: 5. Launch Application
python backend/app.py

if errorlevel 1 (
    echo.
    echo [ERROR] Server exited with an error code.
    pause
)
