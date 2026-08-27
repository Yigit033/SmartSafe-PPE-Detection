# Inno Setup Terminal Derleme Scripti
$ISCC_paths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files\Inno Setup 7\ISCC.exe"
)

$ISCC = $null
foreach ($path in $ISCC_paths) {
    if (Test-Path $path) {
        $ISCC = $path
        break
    }
}

if (-not $ISCC) {
    echo "[HATA] Inno Setup (ISCC.exe) bulunamadi! Lutfen Inno Setup'in kurulu oldugundan emin olun."
    exit
}

echo "---------------------------------------------------"
echo "SmartSafe AI Windows Installer Derleniyor..."
echo "---------------------------------------------------"

# Derleme komutunu calistir
if (Test-Path "setup.iss") {
    & $ISCC "setup.iss"
} elseif (Test-Path "infra/setup.iss") {
    Push-Location "infra"
    try {
        & $ISCC "setup.iss"
    } finally {
        Pop-Location
    }
} else {
    echo "[HATA] setup.iss bulunamadi!"
    exit 1
}

if ($LASTEXITCODE -eq 0) {
    echo "---------------------------------------------------"
    echo "BASARILI: Installer olusturuldu!"
    echo "Dosya: ../landing/public/download/SmartSafe-AI-Setup.exe"
    echo "---------------------------------------------------"
} else {
    echo "[HATA] Derleme sirasinda bir sorun olustu."
}
