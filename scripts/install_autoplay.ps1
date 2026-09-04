$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$AutoplayExe = Join-Path $VenvDir "Scripts\renegade-ai-autoplay.exe"

Write-Host "RenegadeAI v0.5 autoplay setup" -ForegroundColor Cyan
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

$StartupDir = [Environment]::GetFolderPath("Startup")
$LauncherPath = Join-Path $StartupDir "RenegadeAI-Autoplay.cmd"
$Launcher = @"
@echo off
cd /d "$RepoRoot"
start "" /min "$AutoplayExe"
"@
Set-Content -Path $LauncherPath -Value $Launcher -Encoding ASCII

Write-Host "Installed startup watcher:" -ForegroundColor Green
Write-Host "  $LauncherPath"
Write-Host ""
Write-Host "Starting it now. From now on, you only need to open melonDS and load the game."
Start-Process -FilePath $AutoplayExe -WorkingDirectory $RepoRoot -WindowStyle Minimized
Write-Host "Autoplay log: $RepoRoot\runs\autoplay.log"
Write-Host "To remove it later, run scripts\uninstall_autoplay.ps1"
