@echo off
setlocal
title AI-Powered Smart PDS

echo ===================================================
echo   AI-Powered Smart Public Distribution System
echo ===================================================
echo.

cd /d "%~dp0"

if not exist "docker-compose.yml" if not exist "compose.yml" (
    echo [ERROR] Docker Compose file not found.
    echo Keep this BAT file in the Smart PDS project root.
    pause
    exit /b 1
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI is not installed or not in PATH.
    pause
    exit /b 1
)

echo [INFO] Checking Docker Engine...
docker info >nul 2>&1
if not errorlevel 1 goto :docker_ready

echo [INFO] Docker Desktop is not ready. Trying to open it...
powershell -NoProfile -Command "$p=Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'; if(Test-Path $p){Start-Process $p}" >nul 2>&1

echo [INFO] Waiting for Docker Engine [up to 2 minutes]...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ docker info *> $null; if($LASTEXITCODE -eq 0){$ok=$true;break}; Start-Sleep -Seconds 2 }; if($ok){exit 0}else{exit 1}"
if errorlevel 1 (
    echo [ERROR] Docker Engine did not become ready.
    echo Open Docker Desktop, wait until it says Engine running, then retry.
    pause
    exit /b 1
)

:docker_ready
echo [INFO] Docker Engine is ready.
echo.
echo [INFO] Starting Smart PDS and MongoDB with Docker Compose...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] Docker Compose failed to start the services.
    docker compose ps
    docker compose logs --tail=50
    pause
    exit /b 1
)

echo.
echo [INFO] Waiting for Smart PDS health endpoint...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 60;$i++){ try{$r=Invoke-WebRequest -Uri 'http://localhost:5000/api/health' -UseBasicParsing -TimeoutSec 3; if($r.StatusCode -eq 200){$ok=$true;break}}catch{}; Start-Sleep -Seconds 2 }; if($ok){exit 0}else{exit 1}"

if errorlevel 1 (
    echo.
    echo [ERROR] Smart PDS did not become healthy within 2 minutes.
    echo.
    echo [INFO] Container status:
    docker compose ps
    echo.
    echo [INFO] Recent application logs:
    docker compose logs --tail=60 web
    pause
    exit /b 1
)

echo.
echo ===================================================
echo [SUCCESS] Smart PDS is running!
echo.
echo   URL: http://localhost:5000
echo.
echo   Default Credentials:
echo     - Administrator:     admin / admin123
echo     - District Officer:  officer_chennai / officer123
echo     - FPS Dealer:        dealer_001 / dealer123
echo ===================================================
echo.
echo Opening the website in your default browser...
start "" "http://localhost:5000"

echo.
echo You can close this window; Docker containers will keep running.
echo To stop Smart PDS safely, run "docker compose stop" from this folder.
echo MongoDB data and Docker volumes are preserved.
echo.
pause
endlocal
