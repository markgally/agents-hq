# Creates a Desktop shortcut that launches AGENTS HQ with the app icon.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$vbs = Join-Path $root "AGENTS HQ.vbs"
$ico = Join-Path $root "static\icon.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "AGENTS HQ.lnk"

if (-not (Test-Path $vbs)) { throw "Missing AGENTS HQ.vbs at $vbs" }
if (-not (Test-Path $ico)) {
  Write-Host "Generating icons..."
  py -3 (Join-Path $root "tools\make_icons.py")
}

$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($lnkPath)
$s.TargetPath = $vbs
$s.WorkingDirectory = $root
$s.WindowStyle = 7
$s.Description = "AGENTS HQ - Seven Agents. Endless Possibilities."
if (Test-Path $ico) { $s.IconLocation = "$ico,0" }
$s.Save()
Write-Host "Created: $lnkPath"
Write-Host "Double-click the Desktop shortcut to start AGENTS HQ."