<#
.SYNOPSIS
    Launch CERBER Bot via Python launcher with animated banner.
.EXAMPLE
    .\start.ps1
    .\start.ps1 -NoTunnel
    .\start.ps1 -TunnelOnly
#>
param(
    [switch]$NoTunnel,
    [switch]$TunnelOnly
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[!] .venv not found. Run: python -m venv .venv && pip install -e .[dev]" -ForegroundColor Red
    exit 1
}

$pyArgs = @("launcher.py")
if ($NoTunnel)   { $pyArgs += "--no-tunnel" }
if ($TunnelOnly) { $pyArgs += "--tunnel-only" }

& $venvPython @pyArgs
