$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Join-Path $projectRoot "dist\SkillWriterDesktop"
$exePath = Join-Path $appDir "SkillWriterDesktop.exe"
$releaseDir = Join-Path $projectRoot "release"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zipPath = Join-Path $releaseDir "SkillWriterDesktop_$timestamp.zip"

if (-not (Test-Path $exePath)) {
    throw "EXE not found. Build first with build_exe.ps1: $exePath"
}

if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}

Write-Host "[release] packaging: $appDir"
Write-Host "[release] output: $zipPath"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

$maxAttempts = 3
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
        if (Test-Path $zipPath) {
            Remove-Item $zipPath -Force
        }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($appDir, $zipPath)
        break
    } catch {
        if ($attempt -eq $maxAttempts) {
            throw
        }
        Write-Host "[release] packaging failed, retrying..."
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-Path $zipPath)) {
    throw "Release zip was not created: $zipPath"
}

Write-Host "[release] done"
Write-Host "[release] zip: $zipPath"
