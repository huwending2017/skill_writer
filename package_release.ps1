param(
    [switch]$SkipBuild,
    [switch]$KeepExistingZip,
    [int]$KeepReleaseCount = 1
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

function Clear-TransientReleaseArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReleaseDir
    )

    if (-not (Test-Path -LiteralPath $ReleaseDir)) {
        return
    }

    Get-ChildItem -LiteralPath $ReleaseDir -Force -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "_build_*" -or $_.Name -like "_stage_*" -or $_.Name -like "_selftest_*" } |
        ForEach-Object { Remove-PathWithRetry -TargetPath $_.FullName }
}

function Remove-OldReleaseOutputs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReleaseDir,
        [int]$KeepCount = 1
    )

    if ($KeepCount -lt 1) {
        $KeepCount = 1
    }
    if (-not (Test-Path -LiteralPath $ReleaseDir)) {
        return
    }

    $zipFiles = Get-ChildItem -LiteralPath $ReleaseDir -Force -File -Filter "SkillWriterDesktop_*.zip" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    $oldZipFiles = $zipFiles | Select-Object -Skip $KeepCount

    foreach ($zip in $oldZipFiles) {
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($zip.Name)
        $siblings = @(
            $zip.FullName,
            "$($zip.FullName).sha256.txt",
            (Join-Path $ReleaseDir "$baseName.selftest.txt")
        )
        foreach ($path in $siblings) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
            }
        }
    }
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

    foreach ($relative in @("README.md", "clean_workspace.bat", "clean_workspace.ps1")) {
        $source = Join-Path $RootPath $relative
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $TargetPath $relative) -Force
        }
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $TargetPath "data\logs") | Out-Null
    Remove-PythonCaches -RootPath $TargetPath
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
        "RecommendedLauncher: start_skill_writer_desktop.bat",
        "PortableExe: SkillWriterDesktop.exe",
        "RuntimeFolderExe: _runtime\SkillWriterDesktop\SkillWriterDesktop.exe",
        "FolderExeSize: $($exeItem.Length)",
        "Usage:",
        "1. Unzip this package on the target Windows machine.",
        "2. Recommended: double-click start_skill_writer_desktop.bat in the package root.",
        "3. Alternative: double-click SkillWriterDesktop.exe in the package root.",
        "4. Do not enter _runtime and copy/run the small SkillWriterDesktop.exe alone; it must stay beside _runtime\SkillWriterDesktop\_internal.",
        "5. If Windows blocks the program after transfer, right-click the zip or exe, open Properties, choose Unblock, then unzip again.",
        "6. The target machine still needs a working Codex or Claude CLI/login/API-key environment."
    )
    $manifest | Set-Content -LiteralPath $OutputPath -Encoding UTF8
}

function New-RootLauncherBat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$StageDir
    )

    $launcherText = @"
@echo off
setlocal
cd /d "%~dp0"
set "RUNTIME_EXE=%~dp0_runtime\SkillWriterDesktop\SkillWriterDesktop.exe"
set "RUNTIME_PY=%~dp0_runtime\SkillWriterDesktop\_internal\python39.dll"
if not exist "%RUNTIME_EXE%" (
  echo [error] runtime exe not found: %RUNTIME_EXE%
  echo Please unzip the whole release package again.
  pause
  exit /b 1
)
if not exist "%RUNTIME_PY%" (
  echo [error] runtime python not found: %RUNTIME_PY%
  echo Please unzip the whole release package again. Do not copy only the EXE.
  pause
  exit /b 1
)
start "" "%RUNTIME_EXE%"
"@
    $launcherText | Set-Content -Path (Join-Path $StageDir "start_skill_writer_desktop.bat") -Encoding ASCII
}

function New-LauncherBat {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppDir
    )

    $launcherBat = Join-Path $AppDir "start_skill_writer_desktop.bat"
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
}

function Test-ReleasePackage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ZipPath,
        [Parameter(Mandatory = $true)]
        [string]$ExtractPath,
        [Parameter(Mandatory = $true)]
        [string]$ReportPath
    )

    $report = New-Object System.Collections.Generic.List[string]
    $errors = New-Object System.Collections.Generic.List[string]

    function Add-CheckLine {
        param(
            [string]$Status,
            [string]$Message
        )
        $report.Add("[$Status] $Message") | Out-Null
        if ($Status -eq "FAIL") {
            $errors.Add($Message) | Out-Null
        }
    }

    Remove-PathWithRetry -TargetPath $ExtractPath
    New-Item -ItemType Directory -Force -Path $ExtractPath | Out-Null

    try {
        [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $ExtractPath)
    } catch {
        Add-CheckLine -Status "FAIL" -Message ("Unzip release package failed: {0}" -f $_.Exception.Message)
        $report | Set-Content -LiteralPath $ReportPath -Encoding UTF8
        throw "Release self-test failed: unzip failed"
    }

    $requiredFiles = @(
        "SkillWriterDesktop.exe",
        "start_skill_writer_desktop.bat",
        "_runtime\SkillWriterDesktop\SkillWriterDesktop.exe",
        "_runtime\SkillWriterDesktop\start_skill_writer_desktop.bat",
        "_runtime\SkillWriterDesktop\_internal\python39.dll",
        "scripts\run_local_skill_audit.py",
        "scripts\run_local_skill_test.py",
        "scripts\payload_compiler.py",
        "scripts\skill_artifact_utils.py",
        "bundled_skills\family-battle-skill-writer\SKILL.md",
        "RELEASE_NOTES.txt",
        "README.md"
    )

    foreach ($relative in $requiredFiles) {
        $path = Join-Path $ExtractPath $relative
        if (Test-Path -LiteralPath $path) {
            Add-CheckLine -Status "OK" -Message "exists: $relative"
        } else {
            Add-CheckLine -Status "FAIL" -Message "missing: $relative"
        }
    }

    $dataLogs = Join-Path $ExtractPath "data\logs"
    if (Test-Path -LiteralPath $dataLogs) {
        Add-CheckLine -Status "OK" -Message "exists: data\logs"
    } else {
        Add-CheckLine -Status "FAIL" -Message "missing: data\logs"
    }

    $cacheItems = Get-ChildItem -LiteralPath $ExtractPath -Recurse -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "__pycache__" -or $_.Extension -eq ".pyc" }
    if ($cacheItems) {
        Add-CheckLine -Status "FAIL" -Message ("release package contains Python cache files: {0}" -f $cacheItems.Count)
    } else {
        Add-CheckLine -Status "OK" -Message "no __pycache__ / .pyc files"
    }

    $compileTargets = @(
        "scripts\run_local_skill_audit.py",
        "scripts\run_local_skill_test.py",
        "scripts\payload_compiler.py",
        "scripts\skill_artifact_utils.py"
    ) | ForEach-Object { Join-Path $ExtractPath $_ }

    $existingCompileTargets = $compileTargets | Where-Object { Test-Path -LiteralPath $_ }
    if ($existingCompileTargets.Count -gt 0) {
        $compileOutput = & python -B -m py_compile @existingCompileTargets 2>&1
        if ($LASTEXITCODE -eq 0) {
            Add-CheckLine -Status "OK" -Message "core script syntax check passed"
        } else {
            Add-CheckLine -Status "FAIL" -Message ("core script syntax check failed: {0}" -f ($compileOutput | Out-String))
        }
    } else {
        Add-CheckLine -Status "FAIL" -Message "no core scripts found for syntax check"
    }

    $classifierCheck = @'
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
from run_local_skill_test import is_unsupported_embedded_regression_error
samples = [
    'lupa.lua55.LuaError: [string "<python>"]:202: first num should be owner camp value',
    "lupa.lua55.LuaError: service/battle/module/buffs_new/buff_stunt_tianren.lua:93: attempt to index a boolean value (local 'script')",
]
bad_sample = "syntax error near end"
ok = all(is_unsupported_embedded_regression_error(item) for item in samples)
ok = ok and not is_unsupported_embedded_regression_error(bad_sample)
raise SystemExit(0 if ok else 1)
'@
    $classifierOutput = $classifierCheck | & python -B - $ExtractPath 2>&1
    if ($LASTEXITCODE -eq 0) {
        Add-CheckLine -Status "OK" -Message "embedded regression classifier check passed"
    } else {
        Add-CheckLine -Status "FAIL" -Message ("embedded regression classifier check failed: {0}" -f ($classifierOutput | Out-String))
    }

    $zipItem = Get-Item -LiteralPath $ZipPath
    $report.Insert(0, ("ReleaseSelfTest: {0}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))) | Out-Null
    $report.Insert(1, "ZipPath: $ZipPath") | Out-Null
    $report.Insert(2, ("ZipSize: {0}" -f $zipItem.Length)) | Out-Null
    $report.Insert(3, "") | Out-Null
    $report | Set-Content -LiteralPath $ReportPath -Encoding UTF8

    Remove-PythonCaches -RootPath $ExtractPath
    Remove-PathWithRetry -TargetPath $ExtractPath

    if ($errors.Count -gt 0) {
        throw "Release self-test failed. See: $ReportPath"
    }

    Write-Host "[release-selftest] passed: $ReportPath"
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
$releaseBuildDir = Join-Path $releaseDir "_build_$timestamp"
$releaseBuildDist = Join-Path $releaseBuildDir "dist"
$releaseBuildWork = Join-Path $releaseBuildDir "build"
$releasePortableDist = Join-Path $releaseBuildDir "dist_onefile"
$releasePortableWork = Join-Path $releaseBuildDir "build_onefile"
$stageDir = Join-Path $releaseDir "_stage_$timestamp"
$stageAppDir = Join-Path $stageDir "_runtime\SkillWriterDesktop"
$manifestPath = Join-Path $stageDir "RELEASE_NOTES.txt"
$selfTestDir = Join-Path $releaseDir "_selftest_$timestamp"
$selfTestReportPath = Join-Path $releaseDir "SkillWriterDesktop_$timestamp.selftest.txt"

Write-Host "[release] project root: $projectRoot"

if (-not (Test-Path -LiteralPath $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}

trap {
    Write-Host "[release] cleaning transient artifacts after failure"
    Clear-TransientReleaseArtifacts -ReleaseDir $releaseDir
    break
}

Clear-TransientReleaseArtifacts -ReleaseDir $releaseDir
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "dist\scripts")
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "dist\bundled_skills")
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "dist\data")

if (-not $SkipBuild) {
    Write-Host "[release] syncing bundled Codex skills"
    python -B (Join-Path $projectRoot "scripts\sync_bundled_skills.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to sync bundled Codex skills"
    }

    python -B -m PyInstaller --version *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[release] PyInstaller not found, installing from requirements-build.txt"
        python -m pip install -r (Join-Path $projectRoot "requirements-build.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to install build dependencies"
        }
    }

    Remove-PathWithRetry -TargetPath $releaseBuildDir
    New-Item -ItemType Directory -Force -Path $releaseBuildDir | Out-Null

    Write-Host "[release] building folder application in isolated release directory"
    python -B -m PyInstaller --noconfirm --clean --distpath $releaseBuildDist --workpath $releaseBuildWork (Join-Path $projectRoot "SkillWriterDesktop.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Build failed"
    }
    $appDir = Join-Path $releaseBuildDist "SkillWriterDesktop"
    $exePath = Join-Path $appDir "SkillWriterDesktop.exe"

    Write-Host "[release] building single-file portable exe in isolated release directory"
    python -B -m PyInstaller --noconfirm --clean --distpath $releasePortableDist --workpath $releasePortableWork (Join-Path $projectRoot "SkillWriterDesktopPortable.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "Portable build failed"
    }
    $portableExePath = Join-Path $releasePortableDist "SkillWriterDesktopPortable.exe"
} else {
    Write-Host "[release] skip build requested"
}

if (-not (Test-Path -LiteralPath $exePath)) {
    throw "EXE not found. Build first or run without -SkipBuild: $exePath"
}
if (-not (Test-Path -LiteralPath $portableExePath)) {
    throw "Portable EXE not found. Build first or run without -SkipBuild: $portableExePath"
}

Remove-PythonCaches -RootPath $appDir
Remove-PythonCaches -RootPath $portableDist
Remove-PathWithRetry -TargetPath $stageDir
New-Item -ItemType Directory -Path $stageDir | Out-Null
Copy-Item -LiteralPath $appDir -Destination $stageAppDir -Recurse -Force
Copy-Item -LiteralPath $portableExePath -Destination (Join-Path $stageDir "SkillWriterDesktop.exe") -Force
Copy-RuntimeAssets -RootPath $projectRoot -TargetPath $stageDir
New-LauncherBat -AppDir $stageAppDir
New-RootLauncherBat -StageDir $stageDir
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

Write-Host "[release-selftest] extracting and validating release zip"
Test-ReleasePackage -ZipPath $zipPath -ExtractPath $selfTestDir -ReportPath $selfTestReportPath

Remove-PythonCaches -RootPath $projectRoot
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "build")
Remove-PathWithRetry -TargetPath (Join-Path $projectRoot "build_onefile")
Remove-PathWithRetry -TargetPath $releaseBuildDir
Remove-PathWithRetry -TargetPath $selfTestDir
Remove-PathWithRetry -TargetPath $stageDir
Clear-TransientReleaseArtifacts -ReleaseDir $releaseDir
Remove-OldReleaseOutputs -ReleaseDir $releaseDir -KeepCount $KeepReleaseCount

Write-Host "[release] done"
Write-Host "[release] zip: $zipPath"
Write-Host "[release] sha256: $hashPath"
Write-Host "[release] selftest: $selfTestReportPath"
