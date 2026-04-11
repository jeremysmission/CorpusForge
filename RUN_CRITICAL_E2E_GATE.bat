@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: CorpusForge virtual environment not found at .venv\Scripts\python.exe
  exit /b 2
)

".venv\Scripts\python.exe" "tools\run_critical_e2e_gate.py" %*
exit /b %errorlevel%
