@echo off
title Claude Motionreel Generator - Installation
if not exist "%~dp0install.ps1" (
    echo.
    echo Die Datei install.ps1 wurde nicht gefunden.
    echo Bitte die ZIP-Datei zuerst entpacken: Rechtsklick auf die ZIP-Datei, dann "Alle extrahieren".
    echo Danach im entpackten Ordner erneut auf Windows-Installation.bat doppelklicken.
    echo.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
