@echo off
setlocal ENABLEDELAYEDEXPANSION

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install -r requirements.txt
start "NMON Analyzer" http://127.0.0.1:5000/
python app.py
