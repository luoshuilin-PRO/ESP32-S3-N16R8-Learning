param([switch]$SkipTests, [switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
# A launcher can inherit a PowerShell 7-only module path; load Windows PowerShell modules explicitly.
$env:PSModulePath = (Join-Path $PSHOME 'Modules') + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1')
Import-Module (Join-Path $PSHOME 'Modules\CimCmdlets\CimCmdlets.psd1')
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$logDirectory = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory ('install-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
Start-Transcript -LiteralPath $logPath | Out-Null
try {

if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 is required.' }
$os = Get-CimInstance Win32_OperatingSystem
if ([version]$os.Version -lt [version]'10.0.18362') { throw 'Windows 10 1903 or later is required for DirectML.' }

# Verify every copied installer, wheel, and model before executing any installer.
$lines = Get-Content -LiteralPath (Join-Path $root 'asset-hashes.txt')
foreach ($line in $lines) {
    if (-not $line -or $line.StartsWith('#')) { continue }
    if ($line -notmatch '^([0-9A-F]{64})  (.+)$') { throw "Invalid hash line: $line" }
    $relative = $Matches[2]
    $path = [IO.Path]::GetFullPath((Join-Path $root $relative))
    if (-not $path.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe asset path: $relative"
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing asset: $relative" }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $Matches[1]) { throw "Hash mismatch: $relative" }
}
Write-Host 'Offline assets and models verified.'
if ($VerifyOnly) {
    $existingPython = Join-Path $root '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $existingPython) {
        & $existingPython (Join-Path $root 'verify_install.py')
        if ($LASTEXITCODE -ne 0) { throw 'Installed environment check failed.' }
    } else {
        Write-Host 'No installed environment yet; run install.cmd.'
    }
    return
}

$python = Join-Path $root 'runtime\python312\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $candidate = $null
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $candidate = & py -3.12 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -ne 0) { $candidate = $null }
        } catch { $candidate = $null }
    }
    if ($candidate) {
        $python = $candidate.Trim()
    } else {
        $installer = Join-Path $root 'installers\python-3.12.10-amd64.exe'
        if ((Get-AuthenticodeSignature -LiteralPath $installer).Status -ne 'Valid') { throw 'Python installer signature invalid.' }
        $target = Join-Path $root 'runtime\python312'
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        $arguments = '/quiet InstallAllUsers=0 Include_launcher=0 Include_pip=1 Include_tcltk=1 Include_test=0 Shortcuts=0 AssociateFiles=0 PrependPath=0 TargetDir="' + $target + '"'
        $process = Start-Process -FilePath $installer -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -notin @(0, 3010)) { throw "Python installation failed: $($process.ExitCode)" }
        if ($process.ExitCode -eq 3010) { throw 'Restart Windows, then run install.cmd again.' }
    }
}
& $python -c 'import sys,struct,tkinter; assert sys.version_info[:2] == (3,12) and struct.calcsize(chr(80)) == 8'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 with tkinter is required.' }

$vcKey = 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64'
$vc = Get-ItemProperty -Path $vcKey -ErrorAction SilentlyContinue
if (-not $vc -or $vc.Installed -ne 1) {
    $installer = Join-Path $root 'installers\vc_redist.x64.exe'
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw 'Microsoft VC++ installer signature invalid.'
    }
    Write-Host 'Installing Microsoft Visual C++ x64 runtime (Windows may request administrator approval).'
    $process = Start-Process -FilePath $installer -ArgumentList '/install /passive /norestart' -Verb RunAs -Wait -PassThru -WindowStyle Hidden
    if ($process.ExitCode -notin @(0, 3010, 1638)) { throw "VC++ runtime installation failed: $($process.ExitCode)" }
    if ($process.ExitCode -eq 3010) { throw 'Restart Windows, then run install.cmd again.' }
}

$venv = Join-Path $root '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (Test-Path -LiteralPath $venvPython) {
    $venvHealthy = $false
    try {
        & $venvPython -c 'import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize(chr(80)) == 8' 2>$null
        $venvHealthy = $LASTEXITCODE -eq 0
    } catch { $venvHealthy = $false }
    if (-not $venvHealthy) {
        $backup = '.venv-from-old-computer-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
        $backupPath = [IO.Path]::GetFullPath((Join-Path $root $backup))
        if (-not $venv.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -or
            -not $backupPath.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unsafe virtual environment rename.'
        }
        Rename-Item -LiteralPath $venv -NewName $backup
        Write-Host "Unusable copied environment kept as $backup; creating a new one."
    }
}
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& $venvPython -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'Could not bootstrap pip in the virtual environment.' }
& $venvPython -m pip install --no-index --find-links (Join-Path $root 'wheels') --only-binary=:all: --disable-pip-version-check -r (Join-Path $root 'requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Offline dependency installation failed.' }
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }
& $venvPython (Join-Path $root 'verify_install.py')
if ($LASTEXITCODE -ne 0) { throw 'Read-only environment check failed.' }
& $venvPython (Join-Path $root 'firmware-tool\main.py') --self-check
if ($LASTEXITCODE -ne 0) { throw 'Firmware package self-check failed.' }
if (-not $SkipTests) {
    Push-Location $root
    try {
        & $venvPython -m unittest discover -q
        if ($LASTEXITCODE -ne 0) { throw 'Simulated tests failed.' }
    } finally { Pop-Location }
    foreach ($app in @('hid-bridge-diagnostics', 'firmware-tool')) {
        Push-Location (Join-Path $root $app)
        try {
            & $venvPython -m unittest -q
            if ($LASTEXITCODE -ne 0) { throw "Simulated tests failed: $app" }
        } finally { Pop-Location }
    }
}
Write-Host 'Ready. run.cmd starts with COM output disabled.'
} finally {
    Stop-Transcript | Out-Null
}
