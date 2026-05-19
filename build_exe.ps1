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
Remove-PathWithRetry -TargetPath "$projectRoot\dist\SkillWriterDesktop"

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

$exePath = Join-Path $projectRoot "dist\SkillWriterDesktop\SkillWriterDesktop.exe"
$launcherBat = Join-Path $projectRoot "dist\SkillWriterDesktop\start_skill_writer_desktop.bat"
@"
@echo off
setlocal
cd /d "%~dp0"
start "" "%~dp0SkillWriterDesktop.exe"
"@ | Set-Content -Path $launcherBat -Encoding ASCII

Remove-PythonSourceCaches -RootPath $projectRoot
Remove-PathWithRetry -TargetPath "$projectRoot\build"

Write-Host "[build] done"
Write-Host "[build] exe: $exePath"
