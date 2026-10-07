Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Starting AI-Powered Smart Public Distribution System" -ForegroundColor Green
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "URL:   http://localhost:5000" -ForegroundColor Yellow
Write-Host "Login: admin / admin123" -ForegroundColor Yellow
Write-Host ""
Write-Host "Launching web browser automatically in 2 seconds..." -ForegroundColor Cyan
Start-Process "powershell" -ArgumentList "-WindowStyle Hidden -Command Start-Sleep -Seconds 2; Start-Process 'http://localhost:5000'"
python backend/app.py
