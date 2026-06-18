@echo off
echo =======================================================================
echo Starting ProdAI Plant RCA System...
echo =======================================================================
echo.

:: Start LLM/AI backend on port 8000
echo Launching AI Backend (Port 8000)...
start "ProdAI AI Backend" /D "%~dp0llm" ..\.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000
if %ERRORLEVEL% neq 0 (
    echo Failed to start AI Backend.
    pause
    exit /b 1
)

:: Start Web Dashboard on port 8080
echo Launching Web Dashboard (Port 8080)...
start "ProdAI Web Dashboard" /D "%~dp0app" ..\.venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8080
if %ERRORLEVEL% neq 0 (
    echo Failed to start Web Dashboard.
    pause
    exit /b 1
)

echo.
echo All services launched successfully!
echo.
echo - Web Dashboard:  http://localhost:8080
echo - AI Backend API: http://localhost:8000
echo.
echo Default User Credentials:
echo   Email:    admin@plant.com
echo   Password: admin123
echo.
echo Note: To stop the services, simply close the opened command prompt windows.
echo.
pause
