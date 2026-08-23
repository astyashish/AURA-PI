@echo off
setlocal enabledelayedexpansion
title AURA-PI - Starting Up
color 0B
cls

echo.
echo  ===================================================
echo    J . A . R . V . I . S - P I   v2.0
echo    Local AI  ^|  No Cloud  ^|  No Internet Needed
echo  ===================================================
echo.

:: ── 1. Add Ollama to PATH ─────────────────────────────
set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"

:: ── 2. Start Ollama if not running ────────────────────
echo [1/3] Checking Ollama...
curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
if !errorlevel! neq 0 (
    echo       Ollama not running - starting it now...
    start "" /B ollama serve
    goto :wait_ollama
)
echo       Ollama already running.
goto :ollama_ready

:wait_ollama
timeout /t 2 /nobreak >nul
curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>&1
if !errorlevel! neq 0 goto :wait_ollama
echo       Ollama is ready.

:ollama_ready

:: ── 3. Check model ────────────────────────────────────
echo [2/3] Checking model qwen2.5:0.5b...
ollama list 2>nul | findstr /i "qwen2.5" >nul
if !errorlevel! neq 0 (
    echo       Model not found - pulling qwen2.5:0.5b...
    echo       This is a one-time download of about 400 MB.
    ollama pull qwen2.5:0.5b
    if !errorlevel! neq 0 (
        echo       WARNING: Pull failed. Check internet connection.
    )
) else (
    echo       Model ready.
)

:: ── 4. Start Aura ────────────────────────────────────
echo [3/3] Starting Aura web server...
echo.
echo  --------------------------------------------------
echo    Browser  :  http://localhost:5000
echo    Stop     :  Ctrl+C
echo  --------------------------------------------------
echo.

cd /d "%~dp0"
python main.py

if !errorlevel! neq 0 (
    echo.
    echo  [ERROR] Server stopped - exit code !errorlevel!
    echo  See the output above for details.
    echo.
    pause
)
