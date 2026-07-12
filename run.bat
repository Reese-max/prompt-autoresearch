@echo off
title Prompt AutoResearch Launcher

echo ==========================================================
echo    Prompt AutoResearch v2 - Local Server Launcher
echo ==========================================================
echo.

where python3 >nul 2>nul
if %errorlevel% equ 0 goto run_python3

where python >nul 2>nul
if %errorlevel% equ 0 goto run_python

where py >nul 2>nul
if %errorlevel% equ 0 goto run_py

where wsl >nul 2>nul
if %errorlevel% equ 0 goto run_wsl

goto no_python

:run_python3
echo [System] Detected Windows python3, launching server...
python3 run_app.py
if %errorlevel% neq 0 goto run_error
goto end

:run_python
echo [System] Detected Windows python, launching server...
python run_app.py
if %errorlevel% neq 0 goto run_error
goto end

:run_py
echo [System] Detected Windows py launcher, launching server...
py run_app.py
if %errorlevel% neq 0 goto run_error
goto end

:run_wsl
echo [System] Detected WSL environment, launching via WSL python3...
wsl python3 "/mnt/d/Users/Administrator/Desktop/Prompt AutoResearch/run_app.py"
if %errorlevel% neq 0 goto run_error
goto end

:no_python
echo.
echo [ERROR] Python environment not found!
echo Please make sure Python 3 is installed and added to PATH, or WSL is enabled.
echo.
pause
goto end

:run_error
echo.
echo [ERROR] Server failed to start or terminated unexpectedly!
echo Please check the error messages above (e.g. check if port 8000 is occupied).
echo.
pause
goto end

:end
