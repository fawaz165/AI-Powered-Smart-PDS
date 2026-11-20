Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Starting AI-Powered Smart Public Distribution System" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Set working directory to script location
Set-Location -Path $PSScriptRoot

# 1. Parse .env file if present
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if (-not [System.Environment]::GetEnvironmentVariable($k)) {
                [System.Environment]::SetEnvironmentVariable($k, $v)
            }
        }
    }
}

# 2. Port availability helper functions
function Test-PortOccupied([int]$p) {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $iar = $c.BeginConnect('127.0.0.1', $p, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(150, $false) -and $c.Connected) {
            $c.EndConnect($iar)
            $c.Close()
            return $true
        }
        $c.Close()
    } catch {}
    try {
        $l1 = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $p)
        $l1.ExclusiveAddressUse = $true
        $l1.Start()
        $l1.Stop()
    } catch { return $true }
    try {
        $l2 = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $p)
        $l2.ExclusiveAddressUse = $true
        $l2.Start()
        $l2.Stop()
    } catch { return $true }
    return $false
}

function Get-AvailablePort([int]$p, [int]$curOwnerPort = 0) {
    if ($curOwnerPort -gt 0 -and $curOwnerPort -eq $p) { return $p }
    $c = $p
    while (Test-PortOccupied $c) {
        if ($curOwnerPort -gt 0 -and $curOwnerPort -eq $c) { return $c }
        $c++
        if ($c -gt 65535) { break }
    }
    return $c
}

# 3. Resolve application port and automatically allocate available port
$prefAppPort = 5000
if ($env:PORT -and ($env:PORT -as [int])) {
    $prefAppPort = [int]$env:PORT
}

# Stop containerized Flask web container if running to prevent port conflict with native Flask
if (Get-Command docker -ErrorAction SilentlyContinue) {
    try {
        $runningContainers = docker compose ps --services --filter "status=running" 2>$null
        if ($runningContainers -contains "web") {
            Write-Host "[INFO] Stopping containerized Flask web container to prevent port conflict..." -ForegroundColor Yellow
            docker compose stop web | Out-Null
        }
    } catch {}
}

$appPort = Get-AvailablePort $prefAppPort
if ($appPort -ne $prefAppPort) {
    Write-Host "[NOTICE] Application port $prefAppPort is in use by another process. Automatically selected alternative port: $appPort" -ForegroundColor Yellow
}
$env:PORT = "$appPort"

# 4. Resolve MongoDB host port binding and find available port
$prefMongoHostPort = 27018
if ($env:MONGO_PORT_BINDING -match '(\d+)$') {
    $prefMongoHostPort = [int]$matches[1]
}

# Check if local standalone MongoDB is running on 27017
$mongoReady = $false
try {
    $tcp27017 = New-Object System.Net.Sockets.TcpClient
    $tcp27017.Connect('127.0.0.1', 27017)
    $tcp27017.Close()
    Write-Host "[INFO] Local standalone MongoDB detected on 127.0.0.1:27017. Using local instance." -ForegroundColor Green
    $mongoHostPort = 27017
    $env:MONGO_URI = "mongodb://localhost:27017/smart_pds_db"
    $mongoReady = $true
} catch {}

if (-not $mongoReady) {
    $dockerMongoPort = 0
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        try {
            $lines = docker compose ps --format json 2>$null
            if ($lines) {
                foreach ($l in ($lines -split "`r?`n")) {
                    if (-not $l.Trim()) { continue }
                    try {
                        $o = $l | ConvertFrom-Json
                        if ($o.Service -eq 'mongo' -and $o.State -eq 'running') {
                            foreach ($pub in $o.Publishers) {
                                if ($pub.PublishedPort -gt 0) { $dockerMongoPort = [int]$pub.PublishedPort; break }
                            }
                        }
                    } catch {}
                }
            }
        } catch {}
    }

    $mongoHostPort = Get-AvailablePort $prefMongoHostPort $dockerMongoPort
    if ($mongoHostPort -ne $prefMongoHostPort) {
        Write-Host "[NOTICE] Preferred MongoDB host port $prefMongoHostPort is in use. Automatically selected alternative port: $mongoHostPort" -ForegroundColor Yellow
    }
    $env:MONGO_PORT_BINDING = "127.0.0.1:$mongoHostPort"
    $env:MONGO_URI = "mongodb://localhost:$mongoHostPort/smart_pds_db"
}

if (-not $env:DB_NAME) {
    $env:DB_NAME = "smart_pds_db"
}

# 5. Activate Virtual Environment if available
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (.venv)..." -ForegroundColor Gray
    & ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (venv)..." -ForegroundColor Gray
    & ".\venv\Scripts\Activate.ps1"
}

# 6. Ensure MongoDB is active on 127.0.0.1:$mongoHostPort
if (-not $mongoReady) {
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect('127.0.0.1', $mongoHostPort)
        $tcp.Close()
        $mongoReady = $true
    } catch {
        $mongoReady = $false
    }
}

if (-not $mongoReady) {
    Write-Host "[INFO] Starting MongoDB service via Docker Compose (docker compose up -d mongo)..." -ForegroundColor Cyan
    docker compose up -d mongo | Out-Null

    Write-Host "[INFO] Waiting for MongoDB to become ready on 127.0.0.1:$mongoHostPort..." -ForegroundColor Gray
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect('127.0.0.1', $mongoHostPort)
            $tcp.Close()
            $mongoReady = $true
            break
        } catch {}
    }
}

if ($mongoReady) {
    Write-Host "[INFO] MongoDB is active on 127.0.0.1:$mongoHostPort" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Could not confirm MongoDB on 127.0.0.1:$mongoHostPort. Native Flask might fail to connect." -ForegroundColor Red
}

Write-Host ""
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Port Allocation:" -ForegroundColor White
Write-Host "  - Web Application Port:    $appPort" -ForegroundColor White
Write-Host "  - MongoDB Host Port:       $mongoHostPort (mapped to internal 27017)" -ForegroundColor White
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Access URL:  http://localhost:$appPort" -ForegroundColor Yellow
Write-Host ""
Write-Host "Default Accounts:" -ForegroundColor White
Write-Host "  - Administrator:     admin / admin123" -ForegroundColor White
Write-Host "  - District Officer:  officer_chennai / officer123" -ForegroundColor White
Write-Host "  - FPS Dealer:        dealer_001 / dealer123" -ForegroundColor White
Write-Host ""
Write-Host "Waiting for server to be ready before opening browser..." -ForegroundColor Cyan

# 7. Background job to wait until /api/health responds before opening browser
$bgScript = @"
`$ready = `$false
for (`$i = 0; `$i -lt 60; `$i++) {
    try {
        `$r = Invoke-WebRequest -Uri 'http://localhost:$appPort/api/health' -UseBasicParsing -TimeoutSec 3
        if (`$r.StatusCode -eq 200) {
            `$ready = `$true
            break
        }
    } catch {}
    Start-Sleep -Milliseconds 500
}
if (`$ready) {
    Start-Process 'http://localhost:$appPort'
}
"@
Start-Process "powershell" -ArgumentList "-WindowStyle Hidden -Command $bgScript"

# 8. Launch Native Flask Application
python backend/app.py
