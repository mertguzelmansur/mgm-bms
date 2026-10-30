@echo off
REM Eski (tkinter) arayuz - pywebview kurulamazsa
cd /d "%~dp0"
python -m pip install -q bleak
python mgm_bms_klasik.py
