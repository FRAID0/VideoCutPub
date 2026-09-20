@echo off
setlocal enabledelayedexpansion

REM Se placer dans le répertoire du projet de manière dynamique
cd /d "%~dp0"

echo ===================================================
echo   VideoCutPub - Studio de Découpage Video
echo ===================================================

REM Vérifier si l'environnement virtuel venv existe
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creation de l'environnement virtuel venv...
    python -m venv venv
    if errorlevel 1 (
        echo [ERREUR] Impossible de creer l'environnement virtuel. Verifiez que Python 3 est installe.
        pause
        exit /b 1
    )
    echo [INFO] Installation des dependances...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\python.exe -m pip install -r requirements.txt
)

REM Lancer le point d'entree principal
echo [INFO] Lancement de VideoCutPub...
venv\Scripts\python.exe main.py %*

if errorlevel 1 (
    echo [ERREUR] L'application s'est arretee avec une erreur.
    pause
)
