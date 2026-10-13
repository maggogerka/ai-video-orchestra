$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

New-Item -ItemType Directory -Force -Path "logs" | Out-Null
Start-Transcript -Path "logs/generate_test.log" -Append | Out-Null

try {
    if (-not (Test-Path ".venv/Scripts/python.exe")) {
        throw ".venv was not found. Run scripts/bootstrap.ps1 first."
    }
    & .\.venv\Scripts\python.exe -m video_orchestra generate `
        --prompt "A cinematic realistic shot of a lone astronaut walking through a misty pine forest at sunrise, natural motion, detailed lighting" `
        --negative "cartoon, illustration, blurry, low quality, distorted anatomy, text, watermark" `
        --width 480 `
        --height 832 `
        --frames 81 `
        --fps 16 `
        --steps 20 `
        --cfg 5
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
