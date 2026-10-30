@echo off
cd /d "%~dp0"
python uretici.py
if errorlevel 1 pause
