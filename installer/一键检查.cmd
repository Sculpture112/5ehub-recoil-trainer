@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0support-check.ps1" -PackageRoot "%~dp0."
pause
