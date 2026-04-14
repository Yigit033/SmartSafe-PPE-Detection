# Inno Setup Terminal Derleme Scripti
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if (-not (Test-Path $ISCC)) {
    echo "[HATA] Inno Setup (ISCC.exe) bulunamadi! Lutfen Inno Setup'in kurulu oldugundan emin olun."
    exit
}

echo "---------------------------------------------------"
echo "SmartSafe AI Windows Installer Derleniyor..."
echo "---------------------------------------------------"

# Derleme komutunu calistir
Push-Location "infra"
try {
    & $ISCC "setup.iss"
} finally {
    Pop-Location
}

if ($LASTEXITCODE -eq 0) {
    echo "---------------------------------------------------"
    echo "BASARILI: Installer olusturuldu!"
    echo "Dosya: ../landing/public/download/SmartSafe-AI-Setup.exe"
    echo "---------------------------------------------------"
} else {
    echo "[HATA] Derleme sirasinda bir sorun olustu."
}
