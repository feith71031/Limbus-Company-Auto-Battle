@echo off
rem Build both tools into dist\ (run: pip install -r requirements.txt first)
cd /d "%~dp0"
python build.py %*
if errorlevel 1 pause
