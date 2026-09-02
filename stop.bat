@echo off
echo.
echo  Stopping Stock Portfolio Intelligence Platform...
echo.

for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo  Stopping backend (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3000" ^| findstr "LISTENING"') do (
    echo  Stopping frontend (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

echo.
echo  Application stopped.
echo.
pause
