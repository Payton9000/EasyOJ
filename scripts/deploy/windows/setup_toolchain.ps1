param(
    [string]$ProjectRoot = "",
    [string]$MinGWUrl = "https://github.com/brechtsanders/winlibs_mingw/releases/download/14.2.0posix-12.0.0-ucrt-r3/winlibs-x86_64-posix-seh-gcc-14.2.0-mingw-w64ucrt-12.0.0-r3.zip",
    [string]$JdkUrl = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.14%2B7/OpenJDK17U-jdk_x64_windows_hotspot_17.0.14_7.zip",
    [switch]$UseChinaMirror,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$InputRoot)
    if ($InputRoot -and (Test-Path -LiteralPath $InputRoot)) {
        return (Resolve-Path -LiteralPath $InputRoot).Path
    }

    $cwd = (Get-Location).Path
    if (Test-Path -LiteralPath (Join-Path $cwd "run.py")) {
        return $cwd
    }
    if (Test-Path -LiteralPath (Join-Path $cwd "OJ_System\run.py")) {
        return (Join-Path $cwd "OJ_System")
    }

    throw "Cannot locate OJ_System root. Please pass -ProjectRoot explicitly."
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Build-UrlCandidates {
    param(
        [string]$PrimaryUrl,
        [switch]$ChinaMirror
    )

    $urls = New-Object System.Collections.Generic.List[string]
    if ($ChinaMirror) {
        $urls.Add("https://ghfast.top/$PrimaryUrl")
        $urls.Add("https://ghproxy.cn/$PrimaryUrl")
    }
    $urls.Add($PrimaryUrl)
    return $urls
}

function Download-File {
    param(
        [string[]]$Urls,
        [string]$OutFile
    )

    foreach ($url in $Urls) {
        try {
            Write-Host "Downloading: $url"
            Invoke-WebRequest -Uri $url -OutFile $OutFile -UseBasicParsing
            return
        } catch {
            Write-Host "Download failed, trying next source..." -ForegroundColor Yellow
        }
    }

    throw "Failed to download file from all configured sources."
}

function Expand-Zip {
    param(
        [string]$ZipPath,
        [string]$Destination
    )
    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -Recurse -Force -LiteralPath $Destination
    }
    Ensure-Dir -Path $Destination
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $Destination -Force
}

function Get-SingleChildDir {
    param([string]$Path)
    $dirs = Get-ChildItem -LiteralPath $Path -Directory
    if ($dirs.Count -eq 1) {
        return $dirs[0].FullName
    }
    return $null
}

$root = Resolve-ProjectRoot -InputRoot $ProjectRoot
$toolchainDir = Join-Path $root "toolchain"
$tempDir = Join-Path $root ".deploy_tmp"

Ensure-Dir -Path $toolchainDir
Ensure-Dir -Path $tempDir

$mingwZip = Join-Path $tempDir "mingw.zip"
$jdkZip = Join-Path $tempDir "jdk.zip"

$mingwOut = Join-Path $toolchainDir "mingw64"
$jdkOut = Join-Path $toolchainDir "jdk"

if ((Test-Path -LiteralPath $mingwOut) -and -not $Force) {
    Write-Host "MinGW already exists at $mingwOut (use -Force to reinstall)."
} else {
    $mingwUrls = Build-UrlCandidates -PrimaryUrl $MinGWUrl -ChinaMirror:$UseChinaMirror
    Download-File -Urls $mingwUrls -OutFile $mingwZip
    $unpackDir = Join-Path $tempDir "mingw_unpack"
    Expand-Zip -ZipPath $mingwZip -Destination $unpackDir

    $child = Get-SingleChildDir -Path $unpackDir
    if ($child -and (Test-Path -LiteralPath (Join-Path $child "mingw64"))) {
        Move-Item -Force -LiteralPath (Join-Path $child "mingw64") -Destination $mingwOut
    } elseif (Test-Path -LiteralPath (Join-Path $unpackDir "mingw64")) {
        Move-Item -Force -LiteralPath (Join-Path $unpackDir "mingw64") -Destination $mingwOut
    } else {
        if (Test-Path -LiteralPath $mingwOut) {
            Remove-Item -Recurse -Force -LiteralPath $mingwOut
        }
        Move-Item -Force -LiteralPath $unpackDir -Destination $mingwOut
    }
}

if ((Test-Path -LiteralPath $jdkOut) -and -not $Force) {
    Write-Host "JDK already exists at $jdkOut (use -Force to reinstall)."
} else {
    $jdkUrls = Build-UrlCandidates -PrimaryUrl $JdkUrl -ChinaMirror:$UseChinaMirror
    Download-File -Urls $jdkUrls -OutFile $jdkZip
    $jdkUnpack = Join-Path $tempDir "jdk_unpack"
    Expand-Zip -ZipPath $jdkZip -Destination $jdkUnpack

    if (Test-Path -LiteralPath $jdkOut) {
        Remove-Item -Recurse -Force -LiteralPath $jdkOut
    }
    Move-Item -Force -LiteralPath $jdkUnpack -Destination $jdkOut
}

$gppPath = Join-Path $mingwOut "bin\g++.exe"
$javacPath = Join-Path $jdkOut "bin\javac.exe"
if (-not (Test-Path -LiteralPath $javacPath)) {
    $candidate = Get-ChildItem -Path $jdkOut -Recurse -Filter javac.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) {
        $javacPath = $candidate.FullName
    }
}

Write-Host ""
Write-Host "Toolchain setup finished." -ForegroundColor Green
Write-Host "ProjectRoot : $root"
Write-Host "MinGW path  : $mingwOut"
Write-Host "JDK path    : $jdkOut"
Write-Host "g++ exists  : $(Test-Path -LiteralPath $gppPath)"
Write-Host "javac exists: $(Test-Path -LiteralPath $javacPath)"

if (Test-Path -LiteralPath $gppPath) {
    & $gppPath --version | Select-Object -First 1
}
if (Test-Path -LiteralPath $javacPath) {
    & $javacPath -version
}

if (Test-Path -LiteralPath $tempDir) {
    Remove-Item -Recurse -Force -LiteralPath $tempDir
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  d:/EasyOJ/.venv/Scripts/python.exe run.py development"
