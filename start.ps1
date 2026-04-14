<#
.SYNOPSIS
    Launch CERBER Bot with all peripherals and interactive log viewer.
.EXAMPLE
    .\start.ps1
    .\start.ps1 -NoTunnel
    .\start.ps1 -TunnelOnly
#>
param(
    [switch]$NoTunnel,
    [switch]$TunnelOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ProjectRoot

# --- Log directory ---
$LogDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$LogBot      = Join-Path $LogDir "bot.log"
$LogBotErr   = Join-Path $LogDir "bot_error.log"
$LogTunnel   = Join-Path $LogDir "tunnel.log"
$LogLauncher = Join-Path $LogDir "launcher.log"

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $Msg" | Out-File -Append -Encoding UTF8 -FilePath $LogLauncher
}

function Get-EnvValue {
    param([string]$Key, [string]$Default)
    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        $lines = Get-Content $envFile -Encoding UTF8
        foreach ($ln in $lines) {
            if ($ln -match "^\s*$Key\s*=(.*)$") {
                $val = $Matches[1].Trim()
                if ($val) { return $val }
            }
        }
    }
    return $Default
}

function Set-EnvValue {
    param([string]$Key, [string]$Value)
    $envFile = Join-Path $ProjectRoot ".env"
    $lines = Get-Content $envFile -Encoding UTF8
    $found = $false
    $result = @()
    foreach ($ln in $lines) {
        if ($ln -match "^\s*$Key\s*=") {
            $result += "$Key=$Value"
            $found = $true
        }
        else {
            $result += $ln
        }
    }
    if (-not $found) {
        $result += "$Key=$Value"
    }
    $text = ($result -join "`n") + "`n"
    [System.IO.File]::WriteAllText($envFile, $text, [System.Text.UTF8Encoding]::new($false))
}

function Wait-TunnelUrl {
    param([string]$LogFile, [int]$TimeoutSeconds = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $LogFile) {
            $content = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
            if ($content -match "(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)") {
                return $Matches[1]
            }
        }
        Start-Sleep -Milliseconds 500
    }
    return $null
}

function Show-Tail {
    param([string]$File, [int]$Lines = 30, [string]$Label)
    Write-Host ""
    Write-Host "=== $Label (last $Lines lines) ===" -ForegroundColor Cyan
    Write-Host "    File: $File" -ForegroundColor DarkGray
    Write-Host ""
    if (Test-Path $File) {
        $content = Get-Content $File -Tail $Lines -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($content) {
            $content | ForEach-Object { Write-Host "  $_" }
        }
        else {
            Write-Host "  (empty)" -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "  (file not found)" -ForegroundColor DarkGray
    }
    Write-Host ""
}

function Show-Status {
    param($Jobs, [string]$TunnelUrl)
    Write-Host ""
    Write-Host "=== Component Status ===" -ForegroundColor Cyan
    Write-Host ""
    foreach ($entry in $Jobs) {
        $name = $entry.Name
        $proc = $entry.Process
        if ($proc.HasExited) {
            Write-Host "  [$name] STOPPED (exit code $($proc.ExitCode))" -ForegroundColor Red
        }
        else {
            Write-Host "  [$name] RUNNING (PID $($proc.Id))" -ForegroundColor Green
        }
    }
    if ($TunnelUrl) {
        Write-Host ""
        Write-Host "  Tunnel URL: $TunnelUrl" -ForegroundColor DarkCyan
    }
    Write-Host ""
}

function Show-Menu {
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  [1] Bot log          [4] Status" -ForegroundColor White
    Write-Host "  [2] Bot errors       [5] Clear screen" -ForegroundColor White
    Write-Host "  [3] Tunnel log       [Q] Quit" -ForegroundColor White
    Write-Host "  [6] Launcher log" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
}

# --- Preflight checks ---

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[!] .venv not found. Run: python -m venv .venv && pip install -e .[dev]" -ForegroundColor Red
    exit 1
}

$envFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Host "[!] .env not found. Run: Copy-Item .env.example .env" -ForegroundColor Red
    exit 1
}

$token = Get-EnvValue -Key "BOT_TOKEN" -Default ""
if (-not $token -or $token -eq "your_bot_token_from_botfather") {
    Write-Host "[!] BOT_TOKEN not set in .env" -ForegroundColor Red
    exit 1
}

# Reset log files
foreach ($f in @($LogBot, $LogBotErr, $LogTunnel, $LogLauncher)) {
    if (Test-Path $f) { Clear-Content $f }
    else { New-Item -ItemType File -Path $f -Force | Out-Null }
}

Write-Host ""
Write-Host "   CERBER Bot Launcher" -ForegroundColor Green
Write-Host "   ===================" -ForegroundColor Green
Write-Host ""

Write-Log "Launcher started"

$WebPort = Get-EnvValue -Key "WEB_PORT" -Default "8088"
$WebEnabled = Get-EnvValue -Key "WEB_ENABLED" -Default "true"

$components = [System.Collections.ArrayList]::new()
$tunnelUrl = $null

try {
    # -- 1. Cloudflare Tunnel --
    $startTunnel = ((-not $NoTunnel) -and ($WebEnabled -eq "true"))
    if ($startTunnel) {
        if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
            Write-Host "[*] Installing cloudflared..." -ForegroundColor Yellow
            Write-Log "Installing cloudflared"
            winget install Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        }

        Write-Host "[*] Starting Cloudflare Tunnel on port $WebPort..." -ForegroundColor Cyan
        Write-Log "Starting tunnel on port $WebPort"

        $tunnelProc = Start-Process -FilePath "cloudflared" -ArgumentList "tunnel","--url","http://localhost:$WebPort" -PassThru -NoNewWindow -RedirectStandardError $LogTunnel
        [void]$components.Add(@{ Name = "Tunnel"; Process = $tunnelProc })

        Write-Host "    Waiting for tunnel URL..." -ForegroundColor DarkCyan
        $tunnelUrl = Wait-TunnelUrl -LogFile $LogTunnel -TimeoutSeconds 30

        if ($tunnelUrl) {
            Write-Host "    Tunnel: $tunnelUrl" -ForegroundColor Green
            Set-EnvValue -Key "WEB_BASE_URL" -Value $tunnelUrl
            Write-Host "    .env updated automatically" -ForegroundColor DarkCyan
            Write-Log "Tunnel URL: $tunnelUrl -> .env"
        }
        else {
            Write-Host "    [!] Tunnel URL not detected (timeout 30s)" -ForegroundColor Yellow
            Write-Log "Tunnel URL detection timeout"
        }
        Write-Host ""
    }

    # -- 2. Bot + Web --
    if (-not $TunnelOnly) {
        Write-Host "[*] Starting bot..." -ForegroundColor Cyan
        Write-Log "Starting bot"
        if ($WebEnabled -eq "true") {
            Write-Host "    Web: http://localhost:$WebPort" -ForegroundColor DarkCyan
            if ($tunnelUrl) {
                Write-Host "    Mini App: $tunnelUrl" -ForegroundColor DarkCyan
            }
        }

        $botProc = Start-Process -FilePath $venvPython -ArgumentList "-m","cerber_bot" -WorkingDirectory $ProjectRoot -PassThru -NoNewWindow -RedirectStandardOutput $LogBot -RedirectStandardError $LogBotErr
        [void]$components.Add(@{ Name = "Bot"; Process = $botProc })

        Start-Sleep -Seconds 2
        Write-Log "Bot started (PID $($botProc.Id))"
    }

    Write-Host ""
    Write-Host "[OK] All components started." -ForegroundColor Green
    Write-Host "    Logs: $LogDir" -ForegroundColor DarkGray
    Write-Host ""
    Write-Log "All components running"

    # -- Interactive menu loop --
    Show-Menu

    while ($true) {
        Write-Host -NoNewline "> " -ForegroundColor DarkYellow

        # Non-blocking key check with periodic status refresh
        $waitStart = Get-Date
        $key = $null
        while (-not $key) {
            if ([Console]::KeyAvailable) {
                $key = [Console]::ReadKey($true)
                break
            }
            # Check processes every second
            $elapsed = ((Get-Date) - $waitStart).TotalSeconds
            if ($elapsed -gt 5) {
                foreach ($c in $components) {
                    if ($c.Process.HasExited) {
                        Write-Host ""
                        Write-Host "[!] $($c.Name) exited (code $($c.Process.ExitCode))" -ForegroundColor Red
                        Write-Log "$($c.Name) exited unexpectedly: $($c.Process.ExitCode)"
                    }
                }
                $waitStart = Get-Date
            }
            Start-Sleep -Milliseconds 100
        }

        $ch = $key.KeyChar
        Write-Host $ch

        switch ($ch) {
            "1" { Show-Tail -File $LogBot -Lines 40 -Label "Bot Output"; Show-Menu }
            "2" { Show-Tail -File $LogBotErr -Lines 40 -Label "Bot Errors"; Show-Menu }
            "3" { Show-Tail -File $LogTunnel -Lines 40 -Label "Cloudflare Tunnel"; Show-Menu }
            "4" { Show-Status -Jobs $components -TunnelUrl $tunnelUrl; Show-Menu }
            "5" { Clear-Host; Show-Menu }
            "6" { Show-Tail -File $LogLauncher -Lines 40 -Label "Launcher"; Show-Menu }
            "q" { throw "User requested quit" }
            "Q" { throw "User requested quit" }
            default { Write-Host "  Unknown key. Press 1-6 or Q." -ForegroundColor DarkGray }
        }
    }
}
catch {
    Write-Host ""
    Write-Host "[*] Shutting down..." -ForegroundColor Yellow
    Write-Log "Shutdown: $_"
}
finally {
    foreach ($c in $components) {
        if (-not $c.Process.HasExited) {
            Stop-Process -Id $c.Process.Id -Force -ErrorAction SilentlyContinue
            Write-Host "    Stopped: $($c.Name) (PID $($c.Process.Id))" -ForegroundColor DarkYellow
            Write-Log "Stopped $($c.Name) PID $($c.Process.Id)"
        }
    }
    Write-Host ""
    Write-Host "[OK] Done. Logs saved in: $LogDir" -ForegroundColor Green
    Write-Log "Launcher stopped"
}
