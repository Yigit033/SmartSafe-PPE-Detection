@echo off
TITLE SmartSafe AI - Baslatiliyor...
echo ===================================================
echo           SmartSafe AI Kontrol Paneli
echo ===================================================
echo.

:: Docker Kontrolu
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [HATA] Docker bulunamadi! Lutfen Docker Desktop'i yukleyin ve calistirin.
    echo Indirme Adresi: https://www.docker.com/products/docker-desktop
    pause
    exit /b
)

echo [1/3] Guncellemeler denetleniyor...
:: Docker Hub'dan yeni surum varsa ceker
docker compose pull --quiet
if %errorlevel% equ 0 (
    echo [+] Sistem guncel durumda.
) else (
    echo [!] Guncelleme kontrolu atlandi - internet yok veya sunucu mesgul.
)

echo.
echo [2/3] Sistem konteynerlari baslatiliyor...
:: Konteynerlari arka planda baslat
docker compose up -d

if %errorlevel% neq 0 (
    echo [HATA] Konteynerlar baslatilamadi! Docker'in calistigindan emin olun.
    pause
    exit /b
)

echo.
echo [3/3] Tarayici aciliyor...
echo Uygulama hazir! Giris yapabilirsiniz: http://localhost:8088
echo.
echo Loglari gormek icin bu pencereyi acik tutabilirsiniz.
echo Sistemi kapatmak icin Ctrl+C tusuna basin veya bu pencereyi kapatin.
echo.

start http://localhost:8088

:: Loglari takip et
docker compose logs -f
