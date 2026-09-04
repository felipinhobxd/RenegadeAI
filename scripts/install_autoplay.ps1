$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$RenegadeExe = Join-Path $VenvDir "Scripts\renegade-ai.exe"
$AutoplayExe = Join-Path $VenvDir "Scripts\renegade-ai-autoplay.exe"

Write-Host "RenegadeAI v0.6 structured autoplay setup" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Creating .venv automatically..."
    & python -m venv $VenvDir
}

Write-Host "Installing/updating RenegadeAI + vision dependencies..."
$EditableTarget = "${RepoRoot}[dev,vision]"
& $PythonExe -m pip install -e $EditableTarget
if ($LASTEXITCODE -ne 0) {
    throw "pip installation failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path $AutoplayExe)) {
    throw "Autoplay executable was not created: $AutoplayExe"
}

Write-Host ""
Write-Host "Preparing melonDS read-only ARM9 structured state..." -ForegroundColor Cyan
& $RenegadeExe memory configure
if ($LASTEXITCODE -ne 0) {
    Write-Warning "melonDS debugger configuration could not be completed. Vision fallback remains available."
}

$StartupDir = [Environment]::GetFolderPath("Startup")
$LauncherPath = Join-Path $StartupDir "RenegadeAI-Autoplay.cmd"
$Launcher = @"
@echo off
cd /d "$RepoRoot"
start "" /min "$AutoplayExe"
"@
Set-Content -Path $LauncherPath -Value $Launcher -Encoding ASCII

Write-Host ""
Write-Host "Installed startup watcher:" -ForegroundColor Green
Write-Host "  $LauncherPath"
Write-Host ""
Write-Host "Starting it now. After melonDS has been restarted once, RenegadeAI will prefer"
Write-Host "validated read-only RAM state (map/X/Z) and fall back to vision when unavailable."
Start-Process -FilePath $AutoplayExe -WorkingDirectory $RepoRoot -WindowStyle Minimized
Write-Host "Autoplay log: $RepoRoot\runs\autoplay.log"
Write-Host "Structured map: $RepoRoot\data\structured_map.json"
Write-Host "Memory profile: $RepoRoot\data\memory_profile.json"
Write-Host "To remove startup mode later, run scripts\uninstall_autoplay.ps1"
