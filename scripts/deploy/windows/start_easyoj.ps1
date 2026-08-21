param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"
$root = if ($ProjectRoot) {
    (Resolve-Path -LiteralPath $ProjectRoot).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
}

if (-not (Test-Path -LiteralPath (Join-Path $root "run.py") -PathType Leaf) -or
    -not (Test-Path -LiteralPath (Join-Path $root "app") -PathType Container)) {
    throw "Not an EasyOJ project root: $root"
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project Python is missing. Run deploy_gui.py and choose Initialize / repair first."
}

& $python (Join-Path $root "run.py") production
if ($LASTEXITCODE -ne 0) {
    throw "EasyOJ stopped with exit code $LASTEXITCODE"
}
