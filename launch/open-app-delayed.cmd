@echo off
rem Wait for AGENTS HQ to bind the port, then open the app window.
set PORT=%~1
if "%PORT%"=="" set PORT=4181
ping -n 4 127.0.0.1 >nul
call "%~dp0open-app.cmd" %PORT%
