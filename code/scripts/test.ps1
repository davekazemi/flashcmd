$ErrorActionPreference = "Stop"
$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$TestRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
Push-Location $TestRoot
try {
    & $Python -m unittest discover -s tests -v
    $TestExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($TestExitCode -ne 0) { exit $TestExitCode }
