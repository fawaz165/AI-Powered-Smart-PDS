
@echo off
setlocal
title AI-Powered Smart PDS

echo ===================================================
echo   AI-Powered Smart Public Distribution System
echo ===================================================
echo.

cd /d "%~dp0"

:: Check Docker Compose file
if not exist "docker-compose.yml" if not exist "compose.yml" (
    echo ERROR: Docker Compose file not found.
    echo Keep this BAT file in the project root.
    pause
    exit /b 1
)

:: Check Docker installation
where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not installed or not in PATH.
    pause
    exit /b 1
)

:: Check Docker Engine
echo Checking Docker Engine...
docker info >nul 2>&1

if errorlevel 1 (
    echo Starting Docker Desktop...

    if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
        start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    ) else (
        echo Please start Docker Desktop manually.
    )

    echo Waiting for Docker Engine...

    powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ docker info *> $null; if($LASTEXITCODE -eq 0){$ok=$true;break}; Start-Sleep -Seconds 2 }; if($ok){exit 0}else{exit 1}"

    if errorlevel 1 (
        echo ERROR: Docker Engine did not start.
        pause
        exit /b 1
    )
)

echo Docker Engine is ready.
echo.

:: Start application and database
echo Starting Smart PDS containers...
docker compose up -d

if errorlevel 1 (
    echo ERROR: Failed to start Smart PDS.
    docker compose ps
    docker compose logs --tail=50
    pause
    exit /b 1
)

:: Check application health
echo.
echo Waiting for Smart PDS to become healthy...

powershell -NoProfile -Command "$ready=$false; for($i=0;$i -lt 60;$i++){ try{$r=Invoke-WebRequest 'http://localhost:5000/api/health' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200){$ready=$true;break}}catch{}; Start-Sleep -Seconds 2 }; if($ready){exit 0}else{exit 1}"

if errorlevel 1 (
    echo ERROR: Application health check failed.
    docker compose ps
    docker compose logs --tail=60 web
    pause
    exit /b 1
)

:: Open website
echo.
echo ===================================================
echo       SMART PDS STARTED SUCCESSFULLY!
echo ===================================================
echo.
echo Website: http://localhost:5000
echo MongoDB: Docker Container
echo.
echo Opening website...

start "" "http://localhost:5000"

echo.
echo You can close this window.
echo Docker containers will continue running.
echo.
echo To stop Smart PDS safely, run:
echo docker compose stop
echo.
echo Your MongoDB data will be preserved.
echo ===================================================

pause
endlocal
