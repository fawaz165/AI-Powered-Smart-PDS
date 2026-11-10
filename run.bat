@echo off
setlocal EnableExtensions
title AI-Powered Smart PDS

echo ===================================================
echo   AI-Powered Smart Public Distribution System
echo ===================================================
echo.

cd /d "%~dp0"

:: Confirm this launcher is in the project root.
if not exist "docker-compose.yml" if not exist "compose.yml" if not exist "compose.yaml" (
    echo ERROR: Docker Compose file not found.
    echo Keep this BAT file in the Smart PDS project root.
    pause
    exit /b 1
)

:: Check Docker CLI.
where docker >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker CLI is not installed or is not in PATH.
    echo Install Docker Desktop, then reopen this file.
    pause
    exit /b 1
)

:: Start Docker Desktop automatically when the engine is stopped.
echo Checking Docker Engine...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Engine is not running. Launching Docker Desktop...

    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$candidates = @(" ^
      "  (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')," ^
      "  (Join-Path $env:ProgramW6432 'Docker\Docker\Docker Desktop.exe')," ^
      "  (Join-Path $env:LOCALAPPDATA 'Programs\Docker\Docker\Docker Desktop.exe')," ^
      "  (Join-Path $env:LOCALAPPDATA 'Docker\Docker\Docker Desktop.exe')" ^
      ");" ^
      "$exe = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1;" ^
      "if (-not $exe) {" ^
      "  $keys = @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*');" ^
      "  $entry = Get-ItemProperty $keys -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like '*Docker Desktop*' } | Select-Object -First 1;" ^
      "  if ($entry -and $entry.InstallLocation) { $candidate = Join-Path $entry.InstallLocation 'Docker Desktop.exe'; if (Test-Path $candidate) { $exe = $candidate } }" ^
      "};" ^
      "if (-not $exe) { Write-Host 'Could not locate Docker Desktop.exe. Please install Docker Desktop.'; exit 2 };" ^
      "Start-Process -FilePath $exe"

    if errorlevel 1 (
        echo ERROR: Could not launch Docker Desktop.
        pause
        exit /b 1
    )

    echo Waiting for Docker Engine to become ready. This can take a few minutes...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ready=$false; for($i=0; $i -lt 180; $i++) { docker info *> $null; if($LASTEXITCODE -eq 0) { $ready=$true; break }; Start-Sleep -Seconds 2 }; if($ready) { exit 0 } else { exit 1 }"

    if errorlevel 1 (
        echo ERROR: Docker Engine did not become ready within 6 minutes.
        echo Open Docker Desktop and check that its engine has started.
        pause
        exit /b 1
    )
)

echo Docker Engine is ready.
echo.

:: Start the application and database without deleting persistent data.
echo Starting Smart PDS containers...
docker compose up -d
if errorlevel 1 (
    echo ERROR: Failed to start Smart PDS containers.
    docker compose ps
    docker compose logs --tail=60
    pause
    exit /b 1
)

:: Wait for the Flask health endpoint.
echo.
echo Waiting for Smart PDS to become healthy...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ready=$false; for($i=0; $i -lt 90; $i++) { try { $r=Invoke-WebRequest 'http://localhost:5000/api/health' -UseBasicParsing -TimeoutSec 5; if($r.StatusCode -eq 200) { $ready=$true; break } } catch {}; Start-Sleep -Seconds 2 }; if($ready) { exit 0 } else { exit 1 }"

if errorlevel 1 (
    echo ERROR: Smart PDS did not respond successfully.
    docker compose ps
    docker compose logs --tail=80
    pause
    exit /b 1
)

echo.
echo ===================================================
echo       SMART PDS STARTED SUCCESSFULLY!
echo ===================================================
echo.
echo Website: http://localhost:5000
echo.
echo Opening Smart PDS...
start "" "http://localhost:5000"

echo.
echo Docker containers will continue running after this window closes.
echo To stop safely, run: docker compose stop
echo Your MongoDB named volume will be preserved.
echo ===================================================
echo.
pause
endlocal
