@echo off
setlocal

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install pyinstaller
pip install -r requirements.txt
pyinstaller --noconfirm --onefile ^
  --add-data "static;static" ^
  --add-data "templates;templates" ^
  app.py
