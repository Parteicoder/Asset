$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

git pull --ff-only
& $Python scripts\selbsttest.py

Write-Host "Aktualisiert."
