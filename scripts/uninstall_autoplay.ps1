$ErrorActionPreference = "Stop"

$StartupDir = [Environment]::GetFolderPath("Startup")
$LauncherPath = Join-Path $StartupDir "RenegadeAI-Autoplay.cmd"

if (Test-Path $LauncherPath) {
    Remove-Item $LauncherPath -Force
    Write-Host "Removed startup launcher: $LauncherPath" -ForegroundColor Green
} else {
    Write-Host "No RenegadeAI startup launcher was installed."
}

Get-Process -Name "renegade-ai-autoplay" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Autoplay watcher stopped. Local learning/capture data was preserved."
