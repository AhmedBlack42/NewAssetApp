$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$python = Join-Path $appDir '.venv\Scripts\python.exe'
$main = Join-Path $appDir 'main.py'
$env:VIRTUAL_ENV = Join-Path $appDir '.venv'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + ';' + $env:PATH

function Stop-WithMessage([string]$message) {
    Write-Host $message -ForegroundColor Red
    exit 1
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-WithMessage "TrainingDatasetStudio's independent Python environment is missing. Expected: $python"
}
if (-not (Test-Path -LiteralPath $main -PathType Leaf)) {
    Stop-WithMessage "TrainingDatasetStudio entry point is missing: $main"
}

Push-Location -LiteralPath $appDir
try {
    & $python --version
    if ($LASTEXITCODE -ne 0) { throw "Studio Python interpreter failed its startup check (exit code $LASTEXITCODE)." }
    & $python -c "import sys, PySide6, PIL, jsonschema, torch, torchvision, ultralytics; print('TrainingDatasetStudio interpreter: ' + sys.executable); print('Runtime dependencies: PySide6=' + PySide6.__version__ + ', Pillow=' + PIL.__version__ + ', PyTorch=' + torch.__version__ + ', Ultralytics=' + ultralytics.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "Studio dependency startup check failed (exit code $LASTEXITCODE)." }
    & $python $main @args
    $appExit = $LASTEXITCODE
    if ($appExit -ne 0) { throw "TrainingDatasetStudio exited with error code $appExit." }
    exit 0
}
catch {
    Write-Host "TrainingDatasetStudio startup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}

