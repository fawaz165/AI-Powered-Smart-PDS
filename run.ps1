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

# 2. Resolve application port (respecting $env:PORT or .env, defaulting to 5000)
$appPort = 5000
if ($env:PORT -and ($env:PORT -as [int])) {
    $appPort = [int]$env:PORT
}
$env:PORT = "$appPort"

# Resolve MongoDB host port binding (default 27018)
$mongoHostPort = 27018
if ($env:MONGO_PORT_BINDING -match '(\d+)$') {
    $mongoHostPort = [int]$matches[1]
}

# 3. Configure MongoDB connection for native Windows execution
# Ensure native execution uses localhost, pointing to the Docker container host port or local MongoDB
if (-not $env:MONGO_URI -or $env:MONGO_URI -match "mongodb://mongo[:/]") {
    $env:MONGO_URI = "mongodb://localhost:$mongoHostPort/smart_pds_db"
}
if (-not $env:DB_NAME) {
    $env:DB_NAME = "smart_pds_db"
}

# 4. Activate Virtual Environment if available
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (.venv)..." -ForegroundColor Gray
    & ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (venv)..." -ForegroundColor Gray
    & ".\venv\Scripts\Activate.ps1"
}

# 5. Prevent conflict with existing containerized Flask app & check port availability
# If 'web' service is running in Docker Compose, stop it so native Flask can bind to $appPort
if (Get-Command docker -ErrorAction SilentlyContinue) {
    try {
        $runningContainers = docker compose ps --services --filter "status=running" 2>$null
        if ($runningContainers -contains "web") {
            Write-Host "[INFO] Stopping containerized Flask web container to prevent port $appPort conflict..." -ForegroundColor Yellow
            docker compose stop web | Out-Null
        }
    } catch {}
}

# Verify if $appPort is occupied by any external process
$appPortInUse = $false
try {
    $tcpCheck = New-Object System.Net.Sockets.TcpClient
    $tcpCheck.Connect('127.0.0.1', $appPort)
    $tcpCheck.Close()
    $appPortInUse = $true
} catch {
    $appPortInUse = $false
}
if ($appPortInUse) {
    Write-Host "[ERROR] Application port $appPort is already in use by another application or service." -ForegroundColor Red
    Write-Host "Please stop the conflicting process or change PORT=$($appPort + 1) in your .env file." -ForegroundColor Yellow
    exit 1
}

# 6. Check and ensure MongoDB is available on 127.0.0.1:$mongoHostPort
$mongoReady = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect('127.0.0.1', $mongoHostPort)
    $tcp.Close()
    $mongoReady = $true
} catch {
    $mongoReady = $false
}

if (-not $mongoReady) {
    # Check if a standalone MongoDB is already listening on default 27017
    try {
        $tcp27017 = New-Object System.Net.Sockets.TcpClient
        $tcp27017.Connect('127.0.0.1', 27017)
        $tcp27017.Close()
        Write-Host "[INFO] Local standalone MongoDB detected on 127.0.0.1:27017. Using local instance." -ForegroundColor Green
        $mongoHostPort = 27017
        $env:MONGO_URI = "mongodb://localhost:27017/smart_pds_db"
        $mongoReady = $true
    } catch {}
}

if (-not $mongoReady) {
    Write-Host "[INFO] MongoDB is not running on 127.0.0.1:$mongoHostPort." -ForegroundColor Yellow
    if (Get-Command docker -ErrorAction SilentlyContinue) {
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
}

if ($mongoReady) {
    Write-Host "[INFO] MongoDB is active on 127.0.0.1:$mongoHostPort" -ForegroundColor Green
} else {
    Write-Host "[WARNING] Could not confirm MongoDB on 127.0.0.1:$mongoHostPort. Native Flask might fail to connect." -ForegroundColor Red
}

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
