param(
    [string]$ProjectRoot = "",
    [string]$PythonCommand = "",
    [switch]$UseChinaMirror
)

$ErrorActionPreference = "Stop"

function Resolve-EasyOJRoot {
    param([string]$InputRoot)
    if ($InputRoot) {
        $root = (Resolve-Path -LiteralPath $InputRoot).Path
    } else {
        $root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..")).Path
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root "run.py")) -or
        -not (Test-Path -LiteralPath (Join-Path $root "app") -PathType Container)) {
        throw "Not an EasyOJ project root: $root"
    }
    return $root
}

function Invoke-Native {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $FilePath $($Arguments -join ' ')"
    }
}

$root = Resolve-EasyOJRoot -InputRoot $ProjectRoot
$venv = Join-Path $root ".venv"
$localPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $localPython -PathType Leaf)) {
    $bootstrap = $null
    if ($PythonCommand) {
        $bootstrap = (Resolve-Path -LiteralPath $PythonCommand).Path
    } else {
        $bundled = Join-Path $root "runtime\python\python.exe"
        if (Test-Path -LiteralPath $bundled -PathType Leaf) {
            $bootstrap = $bundled
        } else {
            $pythonFromPath = Get-Command "py.exe" -ErrorAction SilentlyContinue
            if ($pythonFromPath) {
                $bootstrap = $pythonFromPath.Source
            } else {
                $pythonFromPath = Get-Command "python.exe" -ErrorAction SilentlyContinue
                if ($pythonFromPath) { $bootstrap = $pythonFromPath.Source }
            }
        }
    }
    if (-not $bootstrap) {
        throw "Python 3.10+ is required once to create the project-local .venv, or bundle runtime\python\python.exe."
    }
    Write-Host "Creating project-local Python environment..."
    Invoke-Native -FilePath $bootstrap -Arguments @("-m", "venv", $venv)
}

if (-not (Test-Path -LiteralPath $localPython -PathType Leaf)) {
    throw "Project-local Python was not created: $localPython"
}

Write-Host "Installing Python dependencies into the project-local environment..."
$wheelhouse = Join-Path $root "vendor\wheels"
if (Test-Path -LiteralPath $wheelhouse -PathType Container) {
    Invoke-Native -FilePath $localPython -Arguments @("-m", "pip", "install", "--no-index", "--find-links", $wheelhouse, "-r", (Join-Path $root "requirements.txt"))
} else {
    Invoke-Native -FilePath $localPython -Arguments @("-m", "pip", "install", "-r", (Join-Path $root "requirements.txt"))
}

$core = Join-Path $root "scripts\deploy\windows\deploy_core.py"
Invoke-Native -FilePath $localPython -Arguments @($core, "--project-root", $root, "--write-env")

$toolchain = Join-Path $root "scripts\deploy\windows\setup_toolchain.ps1"
$toolchainArgs = @("-ProjectRoot", $root)
if ($UseChinaMirror) { $toolchainArgs += "-UseChinaMirror" }
Write-Host "Installing local C++ and Java toolchains..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $toolchain @toolchainArgs
if ($LASTEXITCODE -ne 0) { throw "Toolchain setup failed ($LASTEXITCODE)" }

$gpp = Join-Path $root "toolchain\mingw64\bin\g++.exe"
$javac = Get-ChildItem -LiteralPath (Join-Path $root "toolchain\jdk") -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
$judgePython = Join-Path $root "runtime\python\python.exe"
if (-not (Test-Path -LiteralPath $gpp -PathType Leaf) -or
    -not $javac -or
    -not (Test-Path -LiteralPath $judgePython -PathType Leaf)) {
    throw "Local C++/Java/Python judge runtime verification failed."
}

Write-Host "Local toolchain is ready." -ForegroundColor Green
Write-Host "The launcher will open a setup page in the browser next (administrator account, site name, port)."
