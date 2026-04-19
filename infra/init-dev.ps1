# SmartSafe AI - Yerel Geliştirme Hazırlık Scripti
# Karakter tanımlamaları
$I_n = [char]305  # ı
$i_N = [char]304  # İ
$s_K = [char]351  # ş
$S_B = [char]350  # Ş
$g_Y = [char]287  # ğ
$G_Y = [char]286  # Ğ
$u_K = [char]252  # ü
$U_B = [char]220  # Ü
$o_K = [char]246  # ö
$O_B = [char]214  # Ö
$c_K = [char]231  # ç
$C_B = [char]199  # Ç

function Show-Header($msg) {
    Write-Host "`n>>> $($msg) <<<" -ForegroundColor Cyan
}

# Root dizine çık
$rootDir = Split-Path -Parent $PSScriptRoot

# 0. Port Temizliği
Show-Header "0. Portlar Kontrol Ediliyor (3377, 4477, 5577)..."
$ports = @(3377, 4477, 5577)
foreach ($port in $ports) {
    $proc = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Port $($port) kullanan s$($u_K)rec ($($proc)) durduruluyor..." -ForegroundColor Yellow
        Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue
    }
}

# 1. Encore CLI Kontrolü
if (-not (Get-Command encore -ErrorAction SilentlyContinue)) {
    Show-Header "Encore CLI bulunamad$($I_n), y$($u_K)kleniyor..."
    iwr https://encore.dev/install.ps1 | iex
    $env:Path += ";$env:LOCALAPPDATA\encore\bin"
}

# 1.1 Docker Kontrolü
Show-Header "1. Docker Kontrol Ediliyor..."
$dockerStarted = $false
try {
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Docker $($c_K)al$($I_n)$($s_K)m$($I_n)yor, ba$($s_K)lat$($I_n)l$($I_n)yor..." -ForegroundColor Yellow
        $dockerPath = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerPath) {
            Start-Process $dockerPath
            $dockerStarted = $true
        } else {
            Write-Host "Docker Desktop bulunamad$($I_n)! L$($u_K)tfen manuel olarak ba$($s_K)lat$($I_n)n." -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "Docker zaten $($c_K)al$($I_n)$($s_K)yor." -ForegroundColor Green
    }
} catch {
    Write-Host "Docker kontrol$($u_K) s$($I_n)ras$($I_n)nda hata: $_" -ForegroundColor Red
}

if ($dockerStarted) {
    Write-Host "Docker'$($I_n)n haz$($I_n)r olmas$($I_n) bekleniyor..." -ForegroundColor Yellow
    $retryCount = 0
    while ($retryCount -lt 60) {
        docker info > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Docker haz$($I_n)r!" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 2
        $retryCount++
    }
    if ($retryCount -ge 60) {
        Write-Host "Docker 2 dakika s$($u_K)resince ba$($s_K)layamad$($I_n). Devam edilemiyor." -ForegroundColor Red
        exit 1
    }
}

# 2. Altyapıyı Başlat
Show-Header "2. Altyap$($I_n) Kontrol Ediliyor..."
docker compose -f "$PSScriptRoot/docker-compose.infra-only.yml" up -d

# 3. Python (Core) Kurulumu
Show-Header "2. Core (Python) Kontrol Ediliyor..."
cd "$rootDir/core"
if (-not (Test-Path "venv")) {
    Write-Host "Sanal ortam olu$($s_K)turuluyor..." -ForegroundColor Yellow
    python -m venv venv
    .\venv\Scripts\pip install -r requirements.txt
}

# 4. Backend (Encore) Kontrolü
Show-Header "3. Backend Kontrol Ediliyor..."
cd "$rootDir/backend"
if (-not (Test-Path "node_modules")) {
    Write-Host "Backend paketleri y$($u_K)kleniyor..." -ForegroundColor Yellow
    npm install
}

# Özel migration scriptini çalıştır
Write-Host "Veritaban$($I_n) tablolar$($I_n) olu$($s_K)turuluyor (migrate.cjs)..." -ForegroundColor Yellow
node scripts/migrate.cjs

# 5. Frontend Kurulumu
Show-Header "4. Frontend Kontrol Ediliyor..."
cd "$rootDir/frontend"
if (-not (Test-Path "node_modules")) {
    Write-Host "Frontend paketleri y$($u_K)kleniyor..." -ForegroundColor Yellow
    npm install
}

# Root'a geri dön
cd $rootDir

Show-Header "HAZIR! Sistem ba$($s_K)lat$($I_n)l$($I_n)yor..."
Write-Host "Sistem $($s_K)u an kullan$($I_n)ma haz$($I_n)r." -ForegroundColor Green
