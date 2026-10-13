$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
Start-Transcript -Path "logs/doctor.log" -Append | Out-Null

try {
    if (-not (Test-Path ".venv/Scripts/python.exe")) {
        throw ".venv was not found. Run scripts/bootstrap.ps1 first."
    }
    & .\.venv\Scripts\python.exe -m video_orchestra doctor
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
