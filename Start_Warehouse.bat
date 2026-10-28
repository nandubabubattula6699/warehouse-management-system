@echo off
title Warehouse OS - Server & Dashboard
cd /d "C:\Users\b7580\OneDrive\Desktop\warehouse-management-system"
echo ===================================================
echo   Starting Warehouse OS (Python + PostgreSQL)
echo ===================================================
echo.
echo Database: PostgreSQL (warehouse_db)
echo URL:      http://localhost:8000
echo.
echo Launching server and opening your web browser...
start http://localhost:8000
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
