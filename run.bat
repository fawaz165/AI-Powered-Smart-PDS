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

:: Automatically detect and resolve available host ports for Web and MongoDB
echo Checking port availability...
for /f "usebackq tokens=1,2 delims==" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$prefWeb = [int]'%APP_PORT%';" ^
  "$mongoBind = '%MONGO_BINDING%';" ^
  "$prefMongo = if ($mongoBind -match '(\d+)$') { [int]$matches[1] } else { 27018 };" ^
  "function Test-PortOccupied([int]$p) {" ^
  "  try {" ^
  "    $c = New-Object System.Net.Sockets.TcpClient;" ^
  "    $iar = $c.BeginConnect('127.0.0.1', $p, $null, $null);" ^
  "    if ($iar.AsyncWaitHandle.WaitOne(150, $false) -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true };" ^
  "    $c.Close();" ^
  "  } catch {};" ^
  "  try { $l1 = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $p); $l1.ExclusiveAddressUse = $true; $l1.Start(); $l1.Stop() } catch { return $true };" ^
  "  try { $l2 = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $p); $l2.ExclusiveAddressUse = $true; $l2.Start(); $l2.Stop() } catch { return $true };" ^
  "  return $false;" ^
  "};" ^
  "$dockerWeb = 0; $dockerMongo = 0;" ^
  "if (Get-Command docker -ErrorAction SilentlyContinue) {" ^
  "  try {" ^
  "    $lines = docker compose ps --format json 2>$null;" ^
  "    if ($lines) { foreach ($l in ($lines -split '\r?\n')) {" ^
  "      if (-not $l.Trim()) { continue };" ^
  "      try {" ^
  "        $o = $l | ConvertFrom-Json;" ^
  "        if ($o.Service -eq 'web' -and $o.State -eq 'running') { foreach($pub in $o.Publishers) { if($pub.PublishedPort -gt 0) { $dockerWeb = [int]$pub.PublishedPort; break } } };" ^
  "        if ($o.Service -eq 'mongo' -and $o.State -eq 'running') { foreach($pub in $o.Publishers) { if($pub.PublishedPort -gt 0) { $dockerMongo = [int]$pub.PublishedPort; break } } };" ^
  "      } catch {}" ^
  "    }}" ^
  "  } catch {}" ^
  "};" ^
  "function Get-AvailablePort([int]$p, [int]$cur) {" ^
  "  if ($cur -gt 0 -and $cur -eq $p) { return $p };" ^
  "  $c = $p;" ^
  "  while (Test-PortOccupied $c) {" ^
  "    if ($cur -gt 0 -and $cur -eq $c) { return $c };" ^
  "    $c++;" ^
  "    if ($c -gt 65535) { break };" ^
  "  };" ^
  "  return $c;" ^
  "};" ^
  "$finalWeb = Get-AvailablePort $prefWeb $dockerWeb;" ^
  "$finalMongo = Get-AvailablePort $prefMongo $dockerMongo;" ^
  "if ($finalWeb -ne $prefWeb) { [Console]::Error.WriteLine('[NOTICE] Web port ' + $prefWeb + ' is occupied. Automatically selected available port: ' + $finalWeb) };" ^
  "if ($finalMongo -ne $prefMongo) { [Console]::Error.WriteLine('[NOTICE] MongoDB host port ' + $prefMongo + ' is occupied. Automatically selected available port: ' + $finalMongo) };" ^
  "Write-Output ('APP_PORT=' + $finalWeb);" ^
  "Write-Output ('MONGO_PORT=' + $finalMongo);"` ) do (
    if "%%A"=="APP_PORT" set "APP_PORT=%%B"
    if "%%A"=="MONGO_PORT" set "MONGO_PORT=%%B"
)

:: Export selected ports to environment for Docker Compose
set "PORT=%APP_PORT%"
set "MONGO_PORT_BINDING=127.0.0.1:%MONGO_PORT%"

echo.
echo ===================================================
echo   Port Allocation:
echo   - Web Application Port:    %APP_PORT%
echo   - MongoDB Host Port:       %MONGO_PORT% (mapped to container 27017)
echo ===================================================
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
