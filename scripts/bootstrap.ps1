$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
Start-Transcript -Path "logs/bootstrap.log" -Append | Out-Null

try {
    $pythonLauncher = $null
    $pythonArgs = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -c "import sys; assert sys.version_info[:2] == (3, 11)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $pythonLauncher = "py"
            $pythonArgs = @("-3.11")
        }
    }

    if (-not $pythonLauncher -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $detectedVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($detectedVersion -eq "3.11") {
            $pythonLauncher = "python"
        }
    }

    if (-not $pythonLauncher) {
        throw "Python 3.11 was not found. Install it from python.org and try again."
    }

    if (-not (Test-Path ".venv/Scripts/python.exe")) {
        Write-Host "Creating .venv with Python 3.11..."
        & $pythonLauncher @pythonArgs -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create .venv" }
    }

    & .\.venv\Scripts\python.exe -c "import sys; assert sys.version_info[:2] == (3, 11)"
    if ($LASTEXITCODE -ne 0) {
        throw ".venv does not use Python 3.11. Remove .venv and run bootstrap.ps1 again."
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip" }
    & .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the project" }

    Write-Host "Done. Next: powershell -ExecutionPolicy Bypass -File scripts/doctor.ps1" -ForegroundColor Green
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
