param(
    [string]$Dir = "Asset"
)

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/Parteicoder/Asset.git"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "git fehlt. Bitte installieren: https://git-scm.com"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Error "python fehlt. Bitte installieren: https://python.org"
}
$Python = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

if (Test-Path (Join-Path $Dir ".git")) {
    Write-Error "Verzeichnis '$Dir' existiert bereits. Zum Aktualisieren: cd $Dir; .\update.ps1"
}

git clone $RepoUrl $Dir
Set-Location $Dir
& $Python scripts\selbsttest.py

Write-Host ""
Write-Host "Installiert nach $Dir."
Write-Host "Daten sammeln: cd $Dir; $Python scripts\sammeln.py --land NN"
