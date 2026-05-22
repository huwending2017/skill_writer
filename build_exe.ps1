$ErrorActionPreference = "Stop"

function Remove-PathWithRetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [int]$RetryCount = 5,
        [int]$SleepSeconds = 2
    )

    if (-not (Test-Path $TargetPath)) {
        return
    }

    for ($i = 1; $i -le $RetryCount; $i++) {
        try {
            Remove-Item $TargetPath -Recurse -Force
            return
        } catch {
            if ($i -eq $RetryCount) {
                throw
            }
            Write-Host "[build] path busy, retrying remove: $TargetPath"
            Start-Sleep -Seconds $SleepSeconds
        }
    }
}

function Remove-PythonSourceCaches {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath
    )

    $sourceRoots = @(
        "skill_writer_app",
        "scripts",
        "bundled_skills"
    )
    foreach ($relative in $sourceRoots) {
        $root = Join-Path $RootPath $relative
        if (-not (Test-Path -LiteralPath $root)) {
            continue
        }
        Get-ChildItem -LiteralPath $root -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
        Get-ChildItem -LiteralPath $root -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "[build] project root: $projectRoot"

Write-Host "[build] syncing bundled Codex skills"
python -B "$projectRoot\scripts\sync_bundled_skills.py"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to sync bundled Codex skills"
}

$codexResolveOutput = & python -B "$projectRoot\scripts\ensure_codex_cli.py" --install-if-missing 2>&1
if ($LASTEXITCODE -ne 0) {
    throw ("Failed to prepare Codex CLI:`n" + ($codexResolveOutput | Out-String))
}
if ($codexResolveOutput) {
    $resolvedCodex = ($codexResolveOutput | Select-Object -Last 1).ToString().Trim()
    if ($resolvedCodex) {
        Write-Host "[build] Codex CLI ready: $resolvedCodex"
    }
}

python -B -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[build] PyInstaller not found, installing from requirements-build.txt"
    python -m pip install -r "$projectRoot\requirements-build.txt"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install build dependencies"
    }
}

Write-Host "[build] cleaning source Python caches"
Remove-PythonSourceCaches -RootPath $projectRoot

Write-Host "[build] cleaning old build artifacts"
Remove-PathWithRetry -TargetPath "$projectRoot\build"
Remove-PathWithRetry -TargetPath "$projectRoot\build_onefile"
Remove-PathWithRetry -TargetPath "$projectRoot\dist\SkillWriterDesktop"
Remove-PathWithRetry -TargetPath "$projectRoot\dist_onefile"
Remove-Item -LiteralPath "$projectRoot\dist\SkillWriterDesktopPortable.exe" -Force -ErrorAction SilentlyContinue

$maxBuildAttempts = 3
$buildSucceeded = $false

for ($attempt = 1; $attempt -le $maxBuildAttempts; $attempt++) {
    Write-Host "[build] running PyInstaller (attempt $attempt/$maxBuildAttempts)"
    python -B -m PyInstaller --noconfirm "$projectRoot\SkillWriterDesktop.spec"
    $buildExitCode = $LASTEXITCODE

    $exePath = Join-Path $projectRoot "dist\SkillWriterDesktop\SkillWriterDesktop.exe"
    if (($buildExitCode -eq 0) -and (Test-Path $exePath)) {
        $buildSucceeded = $true
        break
    }

    Write-Host "[build] PyInstaller exit code: $buildExitCode"
    if ($attempt -lt $maxBuildAttempts) {
        Write-Host "[build] retrying after short wait"
        Start-Sleep -Seconds 3
        Remove-PathWithRetry -TargetPath "$projectRoot\build"
        Remove-PathWithRetry -TargetPath "$projectRoot\dist\SkillWriterDesktop"
    }
}

if (-not $buildSucceeded) {
    throw "Build failed after $maxBuildAttempts attempts"
}

function Copy-RuntimeAssets {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath
    )

    $runtimeDirs = @("scripts", "bundled_skills")
    foreach ($relative in $runtimeDirs) {
        $source = Join-Path $RootPath $relative
        if (-not (Test-Path -LiteralPath $source)) {
            continue
        }
        $target = Join-Path $TargetPath $relative
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
        Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    }

    $dataLogs = Join-Path $TargetPath "data\logs"
    New-Item -ItemType Directory -Force -Path $dataLogs | Out-Null
}

$exePath = Join-Path $projectRoot "dist\SkillWriterDesktop\SkillWriterDesktop.exe"
$launcherBat = Join-Path $projectRoot "dist\SkillWriterDesktop\start_skill_writer_desktop.bat"
@"
@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0SkillWriterDesktop.exe" (
  echo [error] SkillWriterDesktop.exe not found.
  pause
  exit /b 1
)
if not exist "%~dp0_internal\python39.dll" (
  echo [error] _internal\python39.dll not found.
  echo Please unzip the whole release package before running. Do not copy only the EXE.
  pause
  exit /b 1
)
if not exist "%~dp0_internal\tcl86t.dll" (
  echo [error] _internal\tcl86t.dll not found.
  echo The release package is incomplete. Please unzip the whole package again.
  pause
  exit /b 1
)
start "" "%~dp0SkillWriterDesktop.exe"
"@ | Set-Content -Path $launcherBat -Encoding ASCII

$portableSucceeded = $false
for ($attempt = 1; $attempt -le $maxBuildAttempts; $attempt++) {
    Write-Host "[build] running PyInstaller portable one-file (attempt $attempt/$maxBuildAttempts)"
    python -B -m PyInstaller --noconfirm --clean --distpath "$projectRoot\dist_onefile" --workpath "$projectRoot\build_onefile" "$projectRoot\SkillWriterDesktopPortable.spec"
    $portableExitCode = $LASTEXITCODE

    $portableSource = Join-Path $projectRoot "dist_onefile\SkillWriterDesktopPortable.exe"
    if (($portableExitCode -eq 0) -and (Test-Path -LiteralPath $portableSource)) {
        $portableSucceeded = $true
        break
    }

    Write-Host "[build] portable PyInstaller exit code: $portableExitCode"
    if ($attempt -lt $maxBuildAttempts) {
        Write-Host "[build] retrying portable build after short wait"
        Start-Sleep -Seconds 3
        Remove-PathWithRetry -TargetPath "$projectRoot\build_onefile"
        Remove-PathWithRetry -TargetPath "$projectRoot\dist_onefile"
    }
}

if (-not $portableSucceeded) {
    throw "Portable build failed after $maxBuildAttempts attempts"
}

$portableExePath = Join-Path $projectRoot "dist\SkillWriterDesktopPortable.exe"
Copy-Item -LiteralPath "$projectRoot\dist_onefile\SkillWriterDesktopPortable.exe" -Destination $portableExePath -Force
Copy-RuntimeAssets -RootPath $projectRoot -TargetPath (Join-Path $projectRoot "dist")

Remove-PythonSourceCaches -RootPath $projectRoot
Remove-PathWithRetry -TargetPath "$projectRoot\build"
Remove-PathWithRetry -TargetPath "$projectRoot\build_onefile"

Write-Host "[build] done"
Write-Host "[build] portable exe: $portableExePath"
Write-Host "[build] folder exe: $exePath"
Write-Host "[build] note: SkillWriterDesktop.exe must stay with its _internal directory; use SkillWriterDesktopPortable.exe when you want a single runnable EXE."
