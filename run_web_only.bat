@echo off
echo =======================================================================
echo Starting ProdAI Plant Web Dashboard Only (Remote AI Backend)...
echo =======================================================================
echo.

:: Set the remote LLM API URL
set LLM_API_URL=http://54.91.201.119:8000

:: Start Web Dashboard on port 8080 using absolute path for python executable
echo Launching Web Dashboard (Port 8080)...
echo Using AI Backend: %LLM_API_URL%
start "ProdAI Web Dashboard" /D "%~dp0app" "%~dp0.venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8080
if %ERRORLEVEL% neq 0 (
    echo Failed to start Web Dashboard.
    pause
    exit /b 1
)

echo.
echo Web Dashboard service launched successfully!
echo.
echo - Web Dashboard:  http://localhost:8080
echo - Remote AI Backend: %LLM_API_URL%
echo.
echo Default User Credentials:
echo   Email:    admin@plant.com
echo   Password: admin123
echo.
pause
