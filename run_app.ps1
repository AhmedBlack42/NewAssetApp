$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$python = Join-Path $appDir '.venv\Scripts\python.exe'
$main = Join-Path $appDir 'main.py'
$env:VIRTUAL_ENV = Join-Path $appDir '.venv'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + ';' + $env:PATH

function Stop-WithMessage([string]$message) {
    Write-Host $message -ForegroundColor Red
    Read-Host 'Press Enter to close this window'
    exit 1
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-WithMessage "NewAssetApp's virtual environment is missing or incomplete. Expected: $python. Create or repair NewAssetApp's .venv before launching."
}
if (-not (Test-Path -LiteralPath $main -PathType Leaf)) {
    Stop-WithMessage "NewAssetApp entry point is missing: $main"
}

Push-Location -LiteralPath $appDir
try {
    & $python --version
    if ($LASTEXITCODE -ne 0) { throw "The NewAssetApp Python interpreter failed its startup check (exit code $LASTEXITCODE)." }
    & $python -c "import sys; print('NewAssetApp interpreter: ' + sys.executable)"
    if ($LASTEXITCODE -ne 0) { throw "The NewAssetApp Python interpreter failed its identity check (exit code $LASTEXITCODE)." }
    & $python $main @args
    $appExit = $LASTEXITCODE
    if ($appExit -ne 0) { throw "NewAssetApp exited with error code $appExit." }
    exit 0
}
catch {
    Write-Host "NewAssetApp startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Read-Host 'Press Enter to close this window'
    exit 1
}
finally {
    Pop-Location
}
