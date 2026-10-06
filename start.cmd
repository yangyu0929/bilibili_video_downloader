@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" launch.py
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\pandaai\Scripts\python.exe" (
      "%USERPROFILE%\.workbuddy\binaries\python\envs\pandaai\Scripts\python.exe" launch.py
    ) else (
      echo Please install Python 3.10+ from https://www.python.org/downloads/
    )
  ) else (
    python launch.py
  )
)
pause
