param(
    [string]$ProjectRoot = "",
    [string]$MinGWUrl = "https://github.com/brechtsanders/winlibs_mingw/releases/download/14.2.0posix-12.0.0-ucrt-r3/winlibs-x86_64-posix-seh-gcc-14.2.0-mingw-w64ucrt-12.0.0-r3.zip",
    [string]$MinGWSha256 = "88868d745b807f083a117ff69348d8bc021ad7389aa503379dbed1866efcaeb9",
    [string]$JdkUrl = "https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.14%2B7/OpenJDK17U-jdk_x64_windows_hotspot_17.0.14_7.zip",
    [string]$JdkSha256 = "dddb108e0bf8c3e3a9c5c782fee5874a6a86d5323189969f17094260cf3a1125",
    [string]$PythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip",
    [string]$PythonSha256 = "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b",
    [switch]$UseChinaMirror,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectRoot {
    param([string]$InputRoot)
    if ($InputRoot -and (Test-Path -LiteralPath $InputRoot -PathType Container)) {
        $root = (Resolve-Path -LiteralPath $InputRoot).Path
    } else {
        $cwd = (Get-Location).Path
        if (Test-Path -LiteralPath (Join-Path $cwd "run.py")) {
            $root = $cwd
        } elseif (Test-Path -LiteralPath (Join-Path $cwd "OJ_System\run.py")) {
            $root = (Resolve-Path -LiteralPath (Join-Path $cwd "OJ_System")).Path
        } else {
            throw "Cannot locate EasyOJ root. Please pass -ProjectRoot explicitly."
        }
    }

    if (-not (Test-Path -LiteralPath (Join-Path $root "run.py") -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $root "app") -PathType Container)) {
        throw "The deployment root must contain run.py and app: $root"
    }
    return (Resolve-Path -LiteralPath $root).Path
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

    # Official plus several China reverse-proxies. Rank-UrlCandidates picks by probe speed.
    $urls = New-Object System.Collections.Generic.List[string]
    $urls.Add($PrimaryUrl)
    $urls.Add("https://ghfast.top/$PrimaryUrl")
    $urls.Add("https://ghproxy.cn/$PrimaryUrl")
    $urls.Add("https://mirror.ghproxy.com/$PrimaryUrl")
    $urls.Add("https://gh-proxy.com/$PrimaryUrl")
    if ($PrimaryUrl -match '^https://github.com/') {
        $urls.Add(($PrimaryUrl -replace '^https://github.com/', 'https://kkgithub.com/'))
    }
    return $urls
}

function Build-PythonUrlCandidates {
    param([string]$PrimaryUrl)

    $urls = New-Object System.Collections.Generic.List[string]
    $urls.Add($PrimaryUrl)
    $urls.Add("https://mirrors.huaweicloud.com/python/3.11.9/python-3.11.9-embed-amd64.zip")
    $urls.Add("https://cdn.npmmirror.com/binaries/python/3.11.9/python-3.11.9-embed-amd64.zip")
    return $urls
}

function Measure-UrlProbe {
    param(
        [string]$Url,
        [int]$ProbeBytes = 262144,
        [int]$TimeoutSeconds = 5
    )

    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("easyoj-probe-" + [guid]::NewGuid().ToString("n"))
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try {
        if ($curl) {
            $end = $ProbeBytes - 1
            & curl.exe -L --fail --silent --show-error --max-time $TimeoutSeconds --range "0-$end" -o $tmp $Url
            if ($LASTEXITCODE -ne 0) {
                return [pscustomobject]@{ Url = $Url; BytesPerSecond = 0 }
            }
        } else {
            $request = [Net.HttpWebRequest]::Create($Url)
            $request.Method = "GET"
            $request.AddRange(0, $ProbeBytes - 1)
            $request.Timeout = $TimeoutSeconds * 1000
            $request.ReadWriteTimeout = $TimeoutSeconds * 1000
            $response = $request.GetResponse()
            try {
                $stream = $response.GetResponseStream()
                $file = [IO.File]::Create($tmp)
                try {
                    $stream.CopyTo($file)
                } finally {
                    $file.Close()
                    $stream.Close()
                }
            } finally {
                $response.Close()
            }
        }
        $sw.Stop()
        $len = 0
        if (Test-Path -LiteralPath $tmp) {
            $len = (Get-Item -LiteralPath $tmp).Length
        }
        if ($len -le 0) {
            return [pscustomobject]@{ Url = $Url; BytesPerSecond = 0 }
        }
        if (-not (Test-ZipMagic -Path $tmp)) {
            return [pscustomobject]@{ Url = $Url; BytesPerSecond = 0 }
        }
        $sec = [Math]::Max($sw.Elapsed.TotalSeconds, 0.001)
        return [pscustomobject]@{ Url = $Url; BytesPerSecond = [int]($len / $sec) }
    } catch {
        return [pscustomobject]@{ Url = $Url; BytesPerSecond = 0 }
    } finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -Force -LiteralPath $tmp -ErrorAction SilentlyContinue
        }
    }
}

function Rank-UrlCandidates {
    param([string[]]$Urls)

    Write-Host "Measuring download sources..."
    $probes = New-Object System.Collections.Generic.List[object]
    foreach ($url in $Urls) {
        $probe = Measure-UrlProbe -Url $url
        $probes.Add($probe)
        if ($probe.BytesPerSecond -gt 0) {
            Write-Host ("  {0:N0} KB/s  {1}" -f ($probe.BytesPerSecond / 1024), $url)
        } else {
            Write-Host ("  unreachable  {0}" -f $url)
        }
    }
    $ranked = @(
        $probes |
            Sort-Object BytesPerSecond -Descending |
            Where-Object { $_.BytesPerSecond -gt 0 } |
            ForEach-Object { $_.Url }
    )
    foreach ($url in $Urls) {
        if ($ranked -notcontains $url) {
            $ranked += $url
        }
    }
    if ($ranked.Count -gt 0) {
        Write-Host "Selected: $($ranked[0])"
    }
    return ,$ranked
}

function Test-ZipMagic {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $stream = [IO.File]::OpenRead($Path)
    try {
        $header = New-Object byte[] 4
        $read = $stream.Read($header, 0, 4)
        return ($read -ge 2 -and $header[0] -eq 0x50 -and $header[1] -eq 0x4B)
    } finally {
        $stream.Close()
    }
}

function Invoke-ResumableCurl {
    param(
        [string]$Url,
        [string]$OutFile
    )
    $maxAttempts = 8
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        $curlArgs = @(
            "-L",
            "--fail",
            "--retry", "2",
            "--retry-all-errors",
            "-C", "-",
            "--progress-bar",
            "--connect-timeout", "30",
            "--http1.1",
            "-o", $OutFile,
            $Url
        )
        & curl.exe @curlArgs
        if ($LASTEXITCODE -eq 0) {
            return
        }
        if ($LASTEXITCODE -in 18, 28, 56) {
            Write-Host "Connection dropped (curl $LASTEXITCODE); resuming $attempt/$maxAttempts..."
            Start-Sleep -Seconds ([Math]::Min(15, 2 * $attempt))
            continue
        }
        throw "curl.exe exited $LASTEXITCODE"
    }
    throw "curl.exe failed after $maxAttempts attempts"
}

function Assert-Sha256 {
    param(
        [string]$Path,
        [string]$ExpectedHash
    )

    if ($ExpectedHash -notmatch '^[0-9a-fA-F]{64}$') {
        throw "A 64-character SHA-256 value is required for $Path."
    }
    $actualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $ExpectedHash.ToLowerInvariant()) {
        throw "SHA-256 mismatch for $Path. Expected $ExpectedHash, received $actualHash."
    }
}

function Download-VerifiedFile {
    param(
        [string[]]$Urls,
        [string]$OutFile,
        [string]$ExpectedHash
    )

    $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
    $Urls = @(Rank-UrlCandidates -Urls $Urls)
    foreach ($url in $Urls) {
        try {
            Write-Host "Downloading: $url"
            if (Test-Path -LiteralPath $OutFile) {
                try {
                    Assert-Sha256 -Path $OutFile -ExpectedHash $ExpectedHash
                    Write-Host "Verified SHA-256: $ExpectedHash"
                    return $true
                } catch {
                    # Keep a partial file so curl.exe can resume with -C -.
                }
            }
            if ($curl) {
                Invoke-ResumableCurl -Url $url -OutFile $OutFile
            } else {
                if (Test-Path -LiteralPath $OutFile) {
                    Remove-Item -Force -LiteralPath $OutFile
                }
                Invoke-WebRequest -Uri $url -OutFile $OutFile -UseBasicParsing
            }
            if (-not (Test-ZipMagic -Path $OutFile)) {
                throw "Downloaded file is not a ZIP archive"
            }
            Assert-Sha256 -Path $OutFile -ExpectedHash $ExpectedHash
            Write-Host "Verified SHA-256: $ExpectedHash"
            return $true
        } catch {
            if (Test-Path -LiteralPath $OutFile) {
                Remove-Item -Force -LiteralPath $OutFile -ErrorAction SilentlyContinue
            }
            Write-Host "Download failed or checksum did not match; trying next source..." -ForegroundColor Yellow
        }
    }

    throw "Failed to download and verify the artifact from all configured sources."
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

$drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($root))
if ($drive.AvailableFreeSpace -lt 1GB) {
    throw "At least 1 GB of free space is required on $($drive.Name) before installing the local toolchain."
}

Ensure-Dir -Path $toolchainDir
Ensure-Dir -Path $tempDir

$mingwZip = Join-Path $tempDir "mingw.zip"
$jdkZip = Join-Path $tempDir "jdk.zip"

$mingwOut = Join-Path $toolchainDir "mingw64"
$jdkOut = Join-Path $toolchainDir "jdk"
$runtimeOut = Join-Path $root "runtime\python"
$verificationMarker = Join-Path $toolchainDir ".easyoj-verified.json"

if (-not $Force -and (Test-Path -LiteralPath $verificationMarker -PathType Leaf)) {
    try {
        $record = Get-Content -Raw -LiteralPath $verificationMarker | ConvertFrom-Json
        if ($record.mingw_sha256 -ne $MinGWSha256 -or
            $record.jdk_sha256 -ne $JdkSha256 -or
            $record.python_sha256 -ne $PythonSha256) {
            throw "The verification record does not match the pinned toolchain hashes."
        }
    } catch {
        Write-Host "Toolchain verification record is invalid; verified repair will be performed." -ForegroundColor Yellow
        $Force = $true
    }
} elseif (-not $Force) {
    Write-Host "No toolchain verification record found; verified repair will be performed." -ForegroundColor Yellow
    $Force = $true
}

$gppExisting = Join-Path $mingwOut "bin\g++.exe"
if ((Test-Path -LiteralPath $gppExisting -PathType Leaf) -and -not $Force) {
    Write-Host "MinGW already exists at $mingwOut (use -Force to reinstall)."
} else {
    $mingwUrls = Build-UrlCandidates -PrimaryUrl $MinGWUrl -ChinaMirror:$UseChinaMirror
    Download-VerifiedFile -Urls $mingwUrls -OutFile $mingwZip -ExpectedHash $MinGWSha256
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

$javacExisting = Get-ChildItem -LiteralPath $jdkOut -Recurse -Filter "javac.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($javacExisting -and -not $Force) {
    Write-Host "JDK already exists at $jdkOut (use -Force to reinstall)."
} else {
    $jdkUrls = Build-UrlCandidates -PrimaryUrl $JdkUrl -ChinaMirror:$UseChinaMirror
    Download-VerifiedFile -Urls $jdkUrls -OutFile $jdkZip -ExpectedHash $JdkSha256
    $jdkUnpack = Join-Path $tempDir "jdk_unpack"
    Expand-Zip -ZipPath $jdkZip -Destination $jdkUnpack

    if (Test-Path -LiteralPath $jdkOut) {
        Remove-Item -Recurse -Force -LiteralPath $jdkOut
    }
    Move-Item -Force -LiteralPath $jdkUnpack -Destination $jdkOut
}

Ensure-Dir -Path (Join-Path $root "runtime")
$pythonZip = Join-Path $tempDir "python-embed.zip"
$pythonExisting = Join-Path $runtimeOut "python.exe"
if ((Test-Path -LiteralPath $pythonExisting -PathType Leaf) -and -not $Force) {
    Write-Host "Embedded Python already exists at $runtimeOut (use -Force to reinstall)."
} else {
    $pythonUrls = Build-PythonUrlCandidates -PrimaryUrl $PythonUrl
    Download-VerifiedFile -Urls $pythonUrls -OutFile $pythonZip -ExpectedHash $PythonSha256
    Expand-Zip -ZipPath $pythonZip -Destination $runtimeOut
}

$gppPath = Join-Path $mingwOut "bin\g++.exe"
$javacPath = Join-Path $jdkOut "bin\javac.exe"
$pythonPath = Join-Path $runtimeOut "python.exe"
if (-not (Test-Path -LiteralPath $javacPath)) {
    $candidate = Get-ChildItem -Path $jdkOut -Recurse -Filter javac.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($candidate) {
        $javacPath = $candidate.FullName
    }
}

if (-not (Test-Path -LiteralPath $gppPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $javacPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Local toolchain/runtime files are incomplete; refusing to execute unverified artifacts."
}

if (-not $Force) {
    $record = Get-Content -Raw -LiteralPath $verificationMarker | ConvertFrom-Json
    $currentGppHash = (Get-FileHash -LiteralPath $gppPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $currentJavacHash = (Get-FileHash -LiteralPath $javacPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $currentPythonHash = (Get-FileHash -LiteralPath $pythonPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($record.gpp_sha256 -ne $currentGppHash -or
        $record.javac_sha256 -ne $currentJavacHash -or
        $record.python_exe_sha256 -ne $currentPythonHash) {
        throw "Installed toolchain files changed after verification. Reinstall with -Force."
    }
}

@{
    mingw_sha256 = $MinGWSha256
    jdk_sha256 = $JdkSha256
    python_sha256 = $PythonSha256
    gpp_sha256 = (Get-FileHash -LiteralPath $gppPath -Algorithm SHA256).Hash.ToLowerInvariant()
    javac_sha256 = (Get-FileHash -LiteralPath $javacPath -Algorithm SHA256).Hash.ToLowerInvariant()
    python_exe_sha256 = (Get-FileHash -LiteralPath $pythonPath -Algorithm SHA256).Hash.ToLowerInvariant()
    verified_at_utc = [DateTime]::UtcNow.ToString('o')
} | ConvertTo-Json | Set-Content -LiteralPath $verificationMarker -Encoding UTF8

Write-Host ""
Write-Host "Toolchain setup finished." -ForegroundColor Green
Write-Host "ProjectRoot : $root"
Write-Host "MinGW path  : $mingwOut"
Write-Host "JDK path    : $jdkOut"
Write-Host "Python path : $runtimeOut"
Write-Host "g++ exists  : $(Test-Path -LiteralPath $gppPath)"
Write-Host "javac exists: $(Test-Path -LiteralPath $javacPath)"
Write-Host "Python exists: $(Test-Path -LiteralPath $pythonPath)"

if (Test-Path -LiteralPath $gppPath) {
    & $gppPath --version | Select-Object -First 1
}
if (Test-Path -LiteralPath $javacPath) {
    & $javacPath -version
}
if (Test-Path -LiteralPath $pythonPath) {
    & $pythonPath --version
}

if (Test-Path -LiteralPath $tempDir) {
    Remove-Item -Recurse -Force -LiteralPath $tempDir
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  d:/EasyOJ/.venv/Scripts/python.exe run.py development"
