@echo off
title AI-Powered Smart PDS Server
echo ===================================================
echo Starting AI-Powered Smart Public Distribution System
echo ===================================================
echo.
echo URL: http://localhost:5000
echo Login: admin / admin123
echo.
echo Waiting for server to be ready before opening browser...

:: Background job: wait until port 5000 is open, then launch browser
start "" powershell -WindowStyle Hidden -Command "$ready=$false; for($i=0; $i -lt 30 -and -not $ready; $i++){ try { $c = New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5000); $c.Close(); $ready=$true } catch { Start-Sleep -Milliseconds 500 } }; if($ready){ Start-Process 'http://localhost:5000' }"

python backend/app.py
pause
