@echo off
title AI-Powered Smart PDS Server
echo ===================================================
echo Starting AI-Powered Smart Public Distribution System
echo ===================================================
echo.
echo URL: http://localhost:5000
echo Login: admin / admin123
echo.
echo Launching web browser automatically in 2 seconds...
start "" powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:5000'"
python backend/app.py
pause
