Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Starting AI-Powered Smart Public Distribution System" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

# Set working directory to script location
Set-Location -Path $PSScriptRoot

# 1. Activate Virtual Environment if available
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (.venv)..." -ForegroundColor Gray
    & ".\.venv\Scripts\Activate.ps1"
} elseif (Test-Path ".\venv\Scripts\Activate.ps1") {
    Write-Host "[INFO] Activating virtual environment (venv)..." -ForegroundColor Gray
    & ".\venv\Scripts\Activate.ps1"
}

# 2. Check MongoDB on port 27017
$mongoReady = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect('127.0.0.1', 27017)
    $tcp.Close()
    $mongoReady = $true
} catch {
    $mongoReady = $false
}

if (-not $mongoReady) {
    Write-Host "[WARNING] MongoDB is not responding on 127.0.0.1:27017." -ForegroundColor Yellow
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "[INFO] Attempting to start smart_pds_mongo container..." -ForegroundColor Gray
        docker start smart_pds_mongo | Out-Null
        Start-Sleep -Seconds 2
    }
}

Write-Host "Access URL:  http://localhost:5000" -ForegroundColor Yellow
Write-Host ""
Write-Host "Default Accounts:" -ForegroundColor White
Write-Host "  - Administrator:     admin / admin123" -ForegroundColor White
Write-Host "  - District Officer:  officer_chennai / officer123" -ForegroundColor White
Write-Host "  - FPS Dealer:        dealer_001 / dealer123" -ForegroundColor White
Write-Host ""
Write-Host "Waiting for server to be ready before opening browser..." -ForegroundColor Cyan

# 3. Background job to wait until port 5000 is listening before opening browser
Start-Process "powershell" -ArgumentList "-WindowStyle Hidden -Command `$ready=`$false; for(`$i=0; `$i -lt 30 -and -not `$ready; `$i++){ try { `$c = New-Object System.Net.Sockets.TcpClient; `$c.Connect('127.0.0.1', 5000); `$c.Close(); `$ready=`$true } catch { Start-Sleep -Milliseconds 500 } }; if(`$ready){ Start-Process 'http://localhost:5000' }"

# 4. Launch Application
python backend/app.py
