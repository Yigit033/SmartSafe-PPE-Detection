# SmartSafe AI - Otomatik Kurulum Scripti
Write-Host "--- SmartSafe AI Core Kurulumu Basliyor ---" -ForegroundColor Cyan

$corePath = "core"
$venvPath = "$corePath\venv"

# 1. venv kontrolü
if (-not (Test-Path $venvPath)) {
    Write-Host "[1/2] Sanal ortam (venv) bulunamadi. Olusturuluyor..." -ForegroundColor Yellow
    python -m venv $venvPath
} else {
    Write-Host "[1/2] Sanal ortam zaten mevcut." -ForegroundColor Green
}

# 2. Gereksinimlerin yuklenmesi
Write-Host "[2/2] Kutuphaneler yukleniyor/guncelleniyor..." -ForegroundColor Yellow
& "$venvPath\Scripts\pip" install -r "$corePath\requirements.txt"

Write-Host "--- Kurulum Tamamlandi! ---" -ForegroundColor Green
Write-Host "Artik 'bun run core' komutunu kullanabilirsiniz." -ForegroundColor White
