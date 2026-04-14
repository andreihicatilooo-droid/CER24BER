# Запуск Cloudflare Tunnel для локальной разработки Mini App.
#
# Использование:
#   .\start_tunnel.ps1            — туннель на порт 8088 (по умолчанию)
#   .\start_tunnel.ps1 -Port 3000 — туннель на другой порт
#
# После запуска скопируйте HTTPS-URL из вывода и вставьте в .env:
#   WEB_BASE_URL=https://xxx.trycloudflare.com

param(
    [int]$Port = 8088
)

$ErrorActionPreference = "Stop"

# Проверяем наличие cloudflared
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared не найден. Установка через winget..." -ForegroundColor Yellow
    winget install Cloudflare.cloudflared --accept-source-agreements --accept-package-agreements
    # Обновляем PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

Write-Host ""
Write-Host "=== CERBER Cloudflare Tunnel ===" -ForegroundColor Green
Write-Host "Порт: $Port" -ForegroundColor Cyan
Write-Host ""
Write-Host "После запуска скопируйте HTTPS-URL и добавьте в .env:" -ForegroundColor Yellow
Write-Host "  WEB_BASE_URL=https://xxx.trycloudflare.com" -ForegroundColor Yellow
Write-Host ""

cloudflared tunnel --url http://localhost:$Port
