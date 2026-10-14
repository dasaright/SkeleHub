@echo off
cd /d "%~dp0"
if exist "%~dp0Skelefarm Hub.exe" (
  start "" "%~dp0Skelefarm Hub.exe"
  exit /b
)
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 "%~dp0hub.pyw"
) else (
  start "" pythonw "%~dp0hub.pyw"
)
