@echo off
REM AsyaFatigueGuard - Surucu Izleme Sistemi baslatici
REM Panel: http://localhost:8010
cd /d "%~dp0"
set AFG_PORT=8010
echo Sunucu baslatiliyor... Panel: http://localhost:8010
start "" "http://localhost:8010"
"C:\Users\berke\.venvs\afg\Scripts\python.exe" -m app.main
pause
