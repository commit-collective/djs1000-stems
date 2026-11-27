# SPDX-License-Identifier: MIT OR Apache-2.0
# Installs stemd on this Windows computer: a Python environment in the repository (.venv), PyTorch for its GPU (or
# its processor), Demucs, and the model's weights. Run it again to update. Nothing outside the repository changes,
# apart from pip's and PyTorch's caches in your user folder.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#   ... -Torch cpu          the processor only, even with an NVIDIA GPU
#   ... -Torch cu130        PyTorch for CUDA 13.0 (an RTX 50 card picks it by itself), cu126 for older cards
#   ... -Python "C:\Python312\python.exe"
param(
    [ValidateSet("auto", "cpu", "cu126", "cu130")] [string]$Torch = "auto",
    [string]$Python = "",
    [string]$Venv = ".venv"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Say($text) { Write-Host "stemd install: $text" }

# A Python from 3.10 on: the py launcher's newest of these first, else python on the PATH. A version that is not there
# makes py print an error, which must not stop this script.
$ErrorActionPreference = "Continue"
if (-not $Python) {
    foreach ($version in "3.12", "3.13", "3.11", "3.10", "3.14") {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $found = & py "-$version" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $found) { $Python = $found.Trim(); break }
        }
    }
}
if (-not $Python -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $ok = & python -c "import sys; print(sys.version_info >= (3, 10))" 2>$null
    if ($ok -eq "True") { $Python = (& python -c "import sys; print(sys.executable)").Trim() }
}
$ErrorActionPreference = "Stop"
if (-not $Python) {
    throw "No Python 3.10 or later found. Install one from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run this again."
}
Say "Python: $Python"

if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Say "making the environment in $Venv"
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }
}
$py = Join-Path $repo "$Venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip could not be updated" }

# PyTorch: the build for the GPU there is, else the processor's
if ($Torch -eq "auto") {
    $Torch = "cpu"
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        # the whole output, then its first line: cutting the pipeline short would make nvidia-smi's exit code -1
        $ErrorActionPreference = "Continue"
        $cap = @(& nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>$null)[0]
        $gpu = @(& nvidia-smi --query-gpu=name --format=csv,noheader 2>$null)[0]
        $ErrorActionPreference = "Stop"
        if ($gpu -and $gpu -notmatch "fail|error") {
            $Torch = "cu126"
            if ($cap -match "^\s*\d+(\.\d+)?\s*$" -and [double]::Parse($cap.Trim(), [Globalization.CultureInfo]::InvariantCulture) -ge 12.0) { $Torch = "cu130" }
            Say "NVIDIA GPU: $($gpu.Trim()) (compute $($cap.Trim()))"
        }
    }
}
Say "PyTorch for: $Torch"
# pip takes a PyTorch of the same version for another build (+cpu for +cu126) as installed: swap it by hand
$ErrorActionPreference = "Continue"
$have = & $py -c "import torch; print(torch.__version__)" 2>$null
$ErrorActionPreference = "Stop"
if ($have -and -not $have.Trim().EndsWith("+$Torch")) {
    Say "replacing PyTorch $($have.Trim())"
    & $py -m pip uninstall --quiet --yes torch torchaudio
}
& $py -m pip install --quiet torch torchaudio --index-url "https://download.pytorch.org/whl/$Torch"
if ($LASTEXITCODE -ne 0) { throw "PyTorch did not install. With an old GPU driver, update it, or run with -Torch cpu" }

Say "Demucs and stemd"
& $py -m pip install --quiet -e ".[demucs]"
if ($LASTEXITCODE -ne 0) { throw "stemd did not install" }

Say "checking, and fetching the model's weights (80 MB, once)"
& "$Venv\Scripts\stemd.exe" check --download
if ($LASTEXITCODE -ne 0) { throw "stemd check failed: see above" }

Say "done. Next:"
Write-Host "  1. Let the unit in, once, in an administrator PowerShell:"
Write-Host "       New-NetFirewallRule -DisplayName stemd -Direction Inbound -Protocol TCP -LocalPort 4790 -Action Allow -Profile Private,Public -RemoteAddress LocalSubnet"
Write-Host "  2. Start it with a word of your own, the same as stems-token on the unit:"
Write-Host "       $Venv\Scripts\stemd serve --token YOURWORD"
