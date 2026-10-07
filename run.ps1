Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Starting AI-Powered Smart Public Distribution System" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "URL:   http://localhost:5000" -ForegroundColor Yellow
Write-Host "Login: admin / admin123" -ForegroundColor Yellow
Write-Host ""
Write-Host "Waiting for server to be ready before opening browser..." -ForegroundColor Cyan

# Background job to wait until port 5000 is listening before opening browser
Start-Process "powershell" -ArgumentList "-WindowStyle Hidden -Command `$ready=`$false; for(`$i=0; `$i -lt 30 -and -not `$ready; `$i++){ try { `$c = New-Object System.Net.Sockets.TcpClient; `$c.Connect('127.0.0.1', 5000); `$c.Close(); `$ready=`$true } catch { Start-Sleep -Milliseconds 500 } }; if(`$ready){ Start-Process 'http://localhost:5000' }"

python backend/app.py
