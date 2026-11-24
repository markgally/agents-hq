@echo off
rem Open AGENTS HQ in a dedicated browser app window. Fallback to a normal tab.
set PORT=%~1
if "%PORT%"=="" set PORT=4181
set URL=http://127.0.0.1:%PORT%

rem Prefer Edge, then Chrome, each in --app mode (no normal browser chrome).
where msedge >nul 2>nul
if not errorlevel 1 (
  start "" msedge --app=%URL%
  exit /b 0
)
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" --app=%URL%
  exit /b 0
)
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" (
  start "" "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" --app=%URL%
  exit /b 0
)
where chrome >nul 2>nul
if not errorlevel 1 (
  start "" chrome --app=%URL%
  exit /b 0
)
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
  start "" "%ProgramFiles%\Google\Chrome\Application\chrome.exe" --app=%URL%
  exit /b 0
)
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
  start "" "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" --app=%URL%
  exit /b 0
)
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
  start "" "%LocalAppData%\Google\Chrome\Application\chrome.exe" --app=%URL%
  exit /b 0
)

rem Last resort: default browser tab.
start "" %URL%
exit /b 0
