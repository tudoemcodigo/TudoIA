@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tudoia.ps1" %*
exit /b %ERRORLEVEL%
