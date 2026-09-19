@echo off
rem Chay phan mem truc tiep tu ma nguon (can Python + cac thu vien trong requirements)
cd /d "%~dp0"
start "" pythonw run_app.py %*
