@echo off
REM Launches the Flask API, React frontend, and YOLO video loop in separate windows.

set "ROOT=%~dp0"

start "Garbage API"      cmd /k "cd /d "%ROOT%Backend" && python api.py"
start "Garbage Frontend" cmd /k "cd /d "%ROOT%Frontend" && npm start"
start "Garbage Camera" cmd /k "cd /d "%ROOT%Backend" && "C:\Users\chpsh\OneDrive\Desktop\sekai\garbage\garbage-detection-sc\.venv\Scripts\python.exe" main.py"
