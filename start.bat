@echo off
rem AGENTS HQ launcher for Windows: double-click this file (or use AGENTS HQ.vbs).
cd /d "%~dp0"
if "%PORT%"=="" set PORT=4181

rem Find a real Python. "where python" is not enough: Windows has a fake python.exe
rem (Microsoft Store stub) that passes "where" but fails when run, so we run it.
set PY=
py -3 --version >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python --version >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

if not exist .env copy .env.example .env >nul
rem Close a leftover AGENTS HQ process still holding the port.
powershell -NoProfile -Command "try{$c=Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($c){Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host 'Closed the previous process on port %PORT%.'; Start-Sleep 1}}catch{}"
echo AGENTS HQ is starting at http://127.0.0.1:%PORT%
echo Keep this window open. Close it to stop AGENTS HQ (including schedules).
echo Seven Agents. Endless Possibilities.
rem Open a dedicated app window after the server is up (Edge, then Chrome, then default browser).
if "%AHQ_NO_OPEN%"=="" start "" /min "%~dp0launch\open-app-delayed.cmd" %PORT%
%PY% -m agent_hq
echo.
echo AGENTS HQ stopped. If you see an error above, send a screenshot to support.
if not "%AHQ_NO_PAUSE%"=="1" pause
exit /b

:nopython
echo.
echo Python 3 was not found on this computer, so AGENTS HQ can't start yet.
echo.
echo 1. Install Python from https://www.python.org/downloads/
echo 2. In the installer, tick "Add python.exe to PATH" at the bottom, then Install.
echo 3. If Windows opens the Microsoft Store when you run python, turn OFF the
echo    python.exe and python3.exe switches in:
echo    Settings - Apps - Advanced app settings - App execution aliases
echo 4. Close this window and double-click AGENTS HQ.vbs (or start.bat) again.
echo.
pause
exit /b 1
