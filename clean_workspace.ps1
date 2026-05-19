param(
    [switch]$KeepUserState
)

$ErrorActionPreference = "Stop"

function Remove-PathInsideRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [switch]$Directory
    )

    if (-not (Test-Path -LiteralPath $TargetPath)) {
        return
    }

    $root = Resolve-Path -LiteralPath $RootPath -ErrorAction Stop
    $target = Resolve-Path -LiteralPath $TargetPath -ErrorAction Stop

    if (-not $target.Path.StartsWith($root.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refuse to remove path outside project root: $($target.Path)"
    }

    if ($Directory) {
        Remove-Item -LiteralPath $target.Path -Recurse -Force
    } else {
        Remove-Item -LiteralPath $target.Path -Force
    }
    Write-Host "[clean] removed: $($target.Path)"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path -LiteralPath $projectRoot -ErrorAction Stop).Path
Write-Host "[clean] project root: $projectRoot"

$generatedDirs = @(
    "build",
    "dist",
    "dist_rebuild",
    "release",
    "logs",
    "session_handoffs",
    "repair_attachments",
    ".pycache_tmp"
)

foreach ($name in $generatedDirs) {
    Remove-PathInsideRoot -RootPath $projectRoot -TargetPath (Join-Path $projectRoot $name) -Directory
}

if (-not $KeepUserState) {
    Remove-PathInsideRoot -RootPath $projectRoot -TargetPath (Join-Path $projectRoot "data") -Directory

    $stateFiles = @(
        "active_task_state.json",
        "history.json",
        "last_codex_message.txt",
        "settings.json",
        "workflow_state.json"
    )

    foreach ($name in $stateFiles) {
        Remove-PathInsideRoot -RootPath $projectRoot -TargetPath (Join-Path $projectRoot $name)
    }
} else {
    Write-Host "[clean] keeping user state files"
}

$cacheDirs = Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
foreach ($dir in $cacheDirs) {
    Remove-PathInsideRoot -RootPath $projectRoot -TargetPath $dir.FullName -Directory
}

$pycacheTmpDirs = Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -Directory -Filter ".pycache_tmp" -ErrorAction SilentlyContinue
foreach ($dir in $pycacheTmpDirs) {
    Remove-PathInsideRoot -RootPath $projectRoot -TargetPath $dir.FullName -Directory
}

$pycFiles = Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -File -Filter "*.pyc" -ErrorAction SilentlyContinue
foreach ($file in $pycFiles) {
    Remove-PathInsideRoot -RootPath $projectRoot -TargetPath $file.FullName
}

Write-Host "[clean] done"
