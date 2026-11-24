# AGENTS HQ hidden supervisor: start server, open app window, stop server when the window closes.
$ErrorActionPreference = "Stop"
$PORT = if ($env:PORT) { [int]$env:PORT } else { 4181 }
$URL = "http://127.0.0.1:$PORT"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$profileDir = Join-Path $env:LOCALAPPDATA "AGENTS-HQ\chromium-profile"

function Show-Error([string]$Message) {
  Add-Type -AssemblyName System.Windows.Forms | Out-Null
  [System.Windows.Forms.MessageBox]::Show($Message, "AGENTS HQ", "OK", "Error") | Out-Null
}

function Stop-PortListener([int]$Port) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in @($conns)) {
      if ($c.OwningProcess) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {}
}

function Find-Python {
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    & py -3 --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return @{ File = $pyLauncher.Source; Args = @("-3", "-m", "agent_hq") }
    }
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    & python --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      return @{ File = $python.Source; Args = @("-m", "agent_hq") }
    }
  }
  return $null
}

function Wait-Health([string]$HealthUrl, [int]$Seconds = 20) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) { return $true }
    } catch {}
    Start-Sleep -Milliseconds 400
  }
  return $false
}

function Find-Browser {
  $edgeCmds = @("msedge")
  foreach ($name in $edgeCmds) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return @{ Path = $cmd.Source; Name = "Edge" } }
  }
  $edgePaths = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
  )
  foreach ($p in $edgePaths) {
    if (Test-Path -LiteralPath $p) { return @{ Path = $p; Name = "Edge" } }
  }

  $chromeCmd = Get-Command chrome -ErrorAction SilentlyContinue
  if ($chromeCmd) { return @{ Path = $chromeCmd.Source; Name = "Chrome" } }
  $chromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
  )
  foreach ($p in $chromePaths) {
    if (Test-Path -LiteralPath $p) { return @{ Path = $p; Name = "Chrome" } }
  }
  return $null
}

Set-Location -LiteralPath $root

$py = Find-Python
if (-not $py) {
  Show-Error "Python 3 was not found. Install it from https://www.python.org/downloads/ (tick Add python.exe to PATH), then try again."
  exit 1
}

if (-not (Test-Path -LiteralPath (Join-Path $root ".env"))) {
  $example = Join-Path $root ".env.example"
  if (Test-Path -LiteralPath $example) {
    Copy-Item -LiteralPath $example -Destination (Join-Path $root ".env")
  }
}

Stop-PortListener -Port $PORT
Start-Sleep -Milliseconds 400

$server = Start-Process -FilePath $py.File -ArgumentList $py.Args -WorkingDirectory $root -WindowStyle Hidden -PassThru
try {
  if (-not (Wait-Health -HealthUrl "$URL/api/health")) {
    Show-Error "AGENTS HQ did not start on $URL. Check that Python can run: py -3 -m agent_hq"
    exit 1
  }

  New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
  $browser = Find-Browser
  if ($browser) {
    $browserArgs = @(
      "--user-data-dir=$profileDir",
      "--no-first-run",
      "--no-default-browser-check",
      "--app=$URL"
    )
    $browserProc = Start-Process -FilePath $browser.Path -ArgumentList $browserArgs -PassThru
    Wait-Process -Id $browserProc.Id
  } else {
    Start-Process $URL | Out-Null
    Add-Type -AssemblyName System.Windows.Forms | Out-Null
    [System.Windows.Forms.MessageBox]::Show(
      "AGENTS HQ is running in your browser.`n`nClick OK to stop AGENTS HQ (including schedules).",
      "AGENTS HQ",
      "OK",
      "Information"
    ) | Out-Null
  }
}
finally {
  Stop-PortListener -Port $PORT
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
  }
}
