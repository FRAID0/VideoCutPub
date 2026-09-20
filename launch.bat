@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creation de l'environnement virtuel venv...
    python -m venv venv
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt imageio-ffmpeg static-ffmpeg
)

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" main.py %*
    exit
) else (
    venv\Scripts\python.exe main.py %*
)
