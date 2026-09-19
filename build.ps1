# Builds a standalone Windows executable into dist\
# Usage:  .\build.ps1          (one file)
#         .\build.ps1 -OneDir  (folder build - use if antivirus blocks the single file)
param([switch]$OneDir)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$mode = if ($OneDir) { "--onedir" } else { "--onefile" }

python -m PyInstaller --noconfirm --clean $mode --windowed `
    --name "PDF Watermark Remover" `
    --paths src `
    --icon "assets\app-icon.ico" `
    --add-data "assets;assets" `
    --exclude-module tkinter `
    --exclude-module pytest `
    --exclude-module matplotlib `
    --exclude-module pandas `
    --exclude-module pyarrow `
    --exclude-module IPython `
    --exclude-module nbformat `
    --exclude-module jedi `
    --exclude-module zmq `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtNetwork `
    --exclude-module PySide6.Qt3DCore `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtWebEngineCore `
    run_app.py

Write-Host ""
Write-Host "Ban build nam trong: $PSScriptRoot\dist" -ForegroundColor Green
