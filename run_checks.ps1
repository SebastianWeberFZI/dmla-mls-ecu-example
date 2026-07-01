$script = Join-Path $PSScriptRoot "check_ecu_mls.py"

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source $script
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $script
    exit $LASTEXITCODE
}

$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $bundledPython) {
    & $bundledPython $script
    exit $LASTEXITCODE
}

Write-Error "Python 3 was not found. Install Python or run check_ecu_mls.py with a Python 3 interpreter."
exit 1
