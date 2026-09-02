@echo off
title Stock Portfolio Intelligence Platform
cd /d "%~dp0"
color 0B

echo.
echo ============================================================
echo    Stock Portfolio Intelligence Platform
echo    One-Click Setup and Launch
echo ============================================================
echo.

echo  [1/7] Checking Python...
where python >nul 2>&1
if not errorlevel 1 goto :python_ok
echo.
echo  ============================================
echo  ERROR: Python is not installed or not in PATH.
echo.
echo  Please install Python from:
echo  https://www.python.org/downloads/
echo.
echo  IMPORTANT: Check "Add Python to PATH" during install.
echo  ============================================
echo.
echo  Press any key to open the Python download page...
pause >nul
start https://www.python.org/downloads/
exit /b 1
:python_ok
echo       OK - Python found.
python --version
echo.

echo  [2/7] Checking Node.js...
where node >nul 2>&1
if not errorlevel 1 goto :node_ok
if exist "C:\Program Files\nodejs\node.exe" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
    goto :node_ok
)
if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" (
    set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
    goto :node_ok
)
echo.
echo  ============================================
echo  ERROR: Node.js is not installed or not in PATH.
echo.
echo  Please install Node.js from:
echo  https://nodejs.org/
echo  (Download the LTS version, accept all defaults)
echo.
echo  After installing, CLOSE this window and run
echo  start.bat again.
echo  ============================================
echo.
echo  Press any key to open the Node.js download page...
pause >nul
start https://nodejs.org/
exit /b 1
:node_ok
echo       OK - Node.js found.
node --version
echo.

echo  [3/7] Checking configuration...
if not exist ".env" (
    echo       Creating configuration file...
    copy .env.example .env >nul 2>&1
    echo       OK - Default configuration created.
) else (
    echo       OK - Configuration exists.
)
if not exist "data" mkdir data
echo.

echo  [4/7] Checking Python packages (first time takes 2-3 min)...
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo       Installing Python packages... please wait...
    python -m pip install -r backend\requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo  ERROR: Installation failed.
        echo  Please right-click start.bat and "Run as Administrator".
        echo.
        pause
        exit /b 1
    )
    echo       OK - Installed.
) else (
    echo       OK - Already installed.
)
echo.

echo  [5/7] Checking Node.js packages (first time takes 2-3 min)...
if not exist "frontend\node_modules" (
    echo       Installing Node packages... please wait...
    pushd frontend
    call npm install --silent
    popd
    if errorlevel 1 (
        echo.
        echo  ERROR: Installation failed.
        echo.
        pause
        exit /b 1
    )
    echo       OK - Installed.
) else (
    echo       OK - Already installed.
)
echo.

echo  [6/7] Stopping any previous instances...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":3000" ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
timeout /t 2 /nobreak >nul
echo       OK - Ready.
echo.

echo  [7/7] Starting application servers...
echo.
echo       Starting backend server (API)...
start "Portfolio-Backend" cmd /k "cd backend && set PYTHONPATH=. && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo       Waiting for backend to start...
set /a _wait_count=0
:wait_backend
timeout /t 1 /nobreak >nul
set /a _wait_count+=1
if %_wait_count% gtr 60 (
  echo       WARNING: Backend did not start within 60 seconds. Continuing anyway...
  goto backend_timeout
)
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait_backend
:backend_timeout
echo       OK - Backend is running!
echo.
echo       Starting frontend server (website)...
start "Portfolio-Frontend" cmd /k "cd frontend && npm run dev -- --webpack"
echo       Waiting for frontend to start (may take 30 seconds)...
set /a _wait_count=0
:wait_frontend
timeout /t 2 /nobreak >nul
set /a _wait_count+=1
if %_wait_count% gtr 30 (
  echo       WARNING: Frontend did not start within 60 seconds. Continuing anyway...
  goto frontend_timeout
)
curl -s http://localhost:3000 >nul 2>&1
if errorlevel 1 goto wait_frontend
:frontend_timeout
echo       OK - Frontend is running!
echo.
timeout /t 2 /nobreak >nul
start http://localhost:3000
echo ============================================================
echo.
echo   ALL DONE! Your browser should open automatically.
echo.
echo   Application URL:  http://localhost:3000
echo   API URL:          http://localhost:8000
echo.
echo   TO UPLOAD YOUR PORTFOLIO:
echo   1. Click "Upload Portfolio CSV" in the top-right
echo   2. Select your Holdings CSV file
echo   3. Click "Parse and Preview"
echo   4. Click "Confirm Import"
echo   5. Click "Refresh Live Prices" on the dashboard
echo.
echo   TO STOP:
echo   Close both command windows that opened, or
echo   double-click stop.bat.
echo.
echo ============================================================
echo.
pause