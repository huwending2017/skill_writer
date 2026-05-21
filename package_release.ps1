param(
    [switch]$SkipBuild,
    [switch]$KeepExistingZip
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Remove-PathWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [int]$RetryCount = 5,
        [int]$SleepSeconds = 2
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return
    }

    for ($i = 1; $i -le $RetryCount; $i++) {
        try {
            Remove-Item -LiteralPath $TargetPath -Recurse -Force
            return
        } catch {
            if ($i -eq $RetryCount) {
                throw
            }
            Write-Host "[release] path busy, retrying remove: $TargetPath"
            Start-Sleep -Seconds $SleepSeconds
        }
    }
}

function Remove-PythonCaches {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    Get-ChildItem -LiteralPath $RootPath -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Get-ChildItem -LiteralPath $RootPath -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
}

function New-ReleaseManifest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppDir,
        [Parameter(Mandatory = $true)]
        [string]$ZipName,
        [Parameter(Mandatory = $true)]
        [string]$OutputPath
    )

    $exePath = Join-Path $AppDir "SkillWriterDesktop.exe"
    $exeItem = Get-Item -LiteralPath $exePath
    $manifest = @(
        "Skill Writer Desktop Release",
        "GeneratedAt: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "ZipName: $ZipName",
        "FolderExe: SkillWriterDesktop\SkillWriterDesktop.exe",
        "FolderExeSize: $($exeItem.Length)",
        "PortableExe: SkillWriterDesktopPortable.exe",
        "Usage:",
        "1. Unzip this package on the target Windows machine.",
        "2. Recommended: run SkillWriterDesktopPortable.exe. It is a single-file build and avoids missing _internal files.",
        "3. Alternative: open the SkillWriterDesktop folder and run start_skill_writer_desktop.bat.",
        "4. Do not copy SkillWriterDesktop\SkillWriterDesktop.exe alone; it must stay beside the SkillWriterDesktop\_internal directory.",
        "5. If Windows blocks the program after transfer, right-click the zip or exe, open Properties, choose Unblock, then unzip again.",
        "6. The target machine still needs a working Codex or Claude CLI/login/API-key environment."
    )
    $manifest | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$appDir = Join-Path $projectRoot "dist\SkillWriterDesktop"
$exePath = Join-Path $appDir "SkillWriterDesktop.exe"
$portableDist = Join-Path $projectRoot "dist_onefile"
$portableExePath = Join-Path $portableDist "SkillWriterDesktopPortable.exe"
$releaseDir = Join-Path $projectRoot "release"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zipName = "SkillWriterDesktop_$timestamp.zip"
$zipPath = Join-Path $releaseDir $zipName
$stageDir = Join-Path $releaseDir "_stage_$timestamp"
$stageAppDir = Join-Path $stageDir "SkillWriterDesktop"
$manifestPath = Join-Path $stageDir "RELEASE_NOTES.txt"

Write-Host "[release] project root: $projectRoot"

if (-not $SkipBuild) {
    Write-Host "[release] building application"
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $projectRoot "build_exe.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed"
    }

    Write-Host "[release] building single-file portable exe"
    Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "build_onefile")
    Remove-PathWithRetry -TargetPath $portableDist
    python -B -m PyInstaller --noconfirm --clean --distpath $portableDist --workpath (Join-Path $projectRoot "build_onefile") (Join-Path $projectRoot "SkillWriterDesktopPortable.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Portable build failed"
    }
} else {
    Write-Host "[release] skip build requested"
}

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "EXE not found. Build first or run without -SkipBuild: $exePath"
}
if (-not (Test-Path -LiteralPath $portableExePath)) {
    throw "Portable EXE not found. Build first or run without -SkipBuild: $portableExePath"
}

if (-not (Test-Path -LiteralPath $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}

Remove-PythonCaches -RootPath $appDir
Remove-PythonCaches -RootPath $portableDist
Remove-PathWithRetry -TargetPath $stageDir
New-Item -ItemType Directory -Path $stageDir | Out-Null
Copy-Item -LiteralPath $appDir -Destination $stageAppDir -Recurse -Force
Copy-Item -LiteralPath $portableExePath -Destination (Join-Path $stageDir "SkillWriterDesktopPortable.exe") -Force
New-ReleaseManifest -AppDir $stageAppDir -ZipName $zipName -OutputPath $manifestPath

if ((Test-Path -LiteralPath $zipPath) -and -not $KeepExistingZip) {
    Remove-Item -LiteralPath $zipPath -Force
}

Write-Host "[release] packaging: $stageDir"
Write-Host "[release] output: $zipPath"

$maxAttempts = 3
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    try {
        if ((Test-Path -LiteralPath $zipPath) -and -not $KeepExistingZip) {
            Remove-Item -LiteralPath $zipPath -Force
        }
        [System.IO.Compression.ZipFile]::CreateFromDirectory($stageDir, $zipPath)
        break
    } catch {
        if ($attempt -eq $maxAttempts) {
            throw
        }
        Write-Host "[release] packaging failed, retrying..."
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-Path -LiteralPath $zipPath)) {
    throw "Release zip was not created: $zipPath"
}

$hash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
$hashPath = "$zipPath.sha256.txt"
"$($hash.Hash)  $zipName" | Set-Content -LiteralPath $hashPath -Encoding ASCII

Remove-PythonCaches -RootPath $projectRoot
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "build")
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "build_onefile")
Remove-PathWithRetry -TargetPath $stageDir

Write-Host "[release] done"
Write-Host "[release] zip: $zipPath"
Write-Host "[release] sha256: $hashPath"
