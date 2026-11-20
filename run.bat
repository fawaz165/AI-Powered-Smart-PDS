@echo off
setlocal EnableExtensions
title AI-Powered Smart PDS

echo ===================================================
echo   AI-Powered Smart Public Distribution System
echo ===================================================
echo.

cd /d "%~dp0"

:: Resolve configured host port from environment or .env file (default: 5000)
set "APP_PORT=%PORT%"
if "%APP_PORT%"=="" (
    if exist ".env" (
        for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
            if /i "%%a"=="PORT" set "APP_PORT=%%b"
        )
    )
)
if "%APP_PORT%"=="" set "APP_PORT=5000"

:: Resolve configured host MongoDB binding from environment or .env file (default: 127.0.0.1:27018)
set "MONGO_BINDING=%MONGO_PORT_BINDING%"
if "%MONGO_BINDING%"=="" (
    if exist ".env" (
        for /f "usebackq tokens=1,2 delims==" %%a in (".env") do (
            if /i "%%a"=="MONGO_PORT_BINDING" set "MONGO_BINDING=%%b"
        )
    )
)
if "%MONGO_BINDING%"=="" set "MONGO_BINDING=127.0.0.1:27018"

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

:: Check for host port conflicts before launching Docker containers
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$appPort = [int]'%APP_PORT%';" ^
  "$mongoBind = '%MONGO_BINDING%';" ^
  "$mongoPort = if ($mongoBind -match '(\d+)$') { [int]$matches[1] } else { 27018 };" ^
  "$hasConflict = $false;" ^
  "function Test-PortOccupied($p) {" ^
  "  try { $t = New-Object System.Net.Sockets.TcpClient; $t.Connect('127.0.0.1', $p); $t.Close(); return $true } catch { return $false }" ^
  "};" ^
  "$dockerWebRunning = $false;" ^
  "$dockerMongoRunning = $false;" ^
  "if (Get-Command docker -ErrorAction SilentlyContinue) {" ^
  "  try {" ^
  "    $running = docker compose ps --services --filter 'status=running' 2>$null;" ^
  "    if ($running -contains 'web') { $dockerWebRunning = $true };" ^
  "    if ($running -contains 'mongo') { $dockerMongoRunning = $true }" ^
  "  } catch {}" ^
  "};" ^
  "if (-not $dockerWebRunning -and (Test-PortOccupied $appPort)) {" ^
  "  Write-Host 'ERROR: Application port ' $appPort ' is already occupied by another service.' -ForegroundColor Red;" ^
  "  Write-Host 'To resolve this conflict, please stop the conflicting process or change PORT=' ($appPort + 1) ' in your .env file.' -ForegroundColor Yellow;" ^
  "  $hasConflict = $true" ^
  "};" ^
  "if (-not $dockerMongoRunning -and (Test-PortOccupied $mongoPort)) {" ^
  "  Write-Host 'ERROR: MongoDB host port ' $mongoPort ' is already occupied by another service.' -ForegroundColor Red;" ^
  "  Write-Host 'To resolve this conflict, set MONGO_PORT_BINDING=127.0.0.1:' ($mongoPort + 1) ' in your .env file.' -ForegroundColor Yellow;" ^
  "  $hasConflict = $true" ^
  "};" ^
  "if ($hasConflict) { exit 1 } else { exit 0 }"

if errorlevel 1 (
    echo.
    echo Please resolve the port conflict above before continuing.
    pause
    exit /b 1
)

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
echo Waiting for Smart PDS to become healthy on port %APP_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = '%APP_PORT%'; $ready=$false; for($i=0; $i -lt 90; $i++) { try { $r=Invoke-WebRequest \"http://localhost:$port/api/health\" -UseBasicParsing -TimeoutSec 5; if($r.StatusCode -eq 200) { $ready=$true; break } } catch {}; Start-Sleep -Seconds 2 }; if($ready) { exit 0 } else { exit 1 }"

if errorlevel 1 (
    echo ERROR: Smart PDS did not respond successfully on port %APP_PORT%.
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
echo Website: http://localhost:%APP_PORT%
echo.
echo Opening Smart PDS...
start "" "http://localhost:%APP_PORT%"

echo.
echo Docker containers will continue running after this window closes.
echo To stop safely, run: docker compose stop
echo Your MongoDB named volume will be preserved.
echo ===================================================
echo.
pause
endlocal
