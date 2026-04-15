# Karakter kodları ile Türkçe güvenliği
$S_buyuk = [char]350
$s_kucuk = [char]351
$I_noktali = [char]304
$i_noktasiz = [char]305
$G_yumusak = [char]286
$g_yumusak = [char]287
$u_kucuk = [char]252
$o_kucuk = [char]246
$c_kucuk = [char]231
$version = "v0.4.16"
$searchPaths = @(
    (Join-Path $PSScriptRoot "VERSION"),
    (Join-Path (Split-Path $PSScriptRoot -Parent) "VERSION"),
    (Join-Path (Get-Location) "VERSION"),
    (Join-Path (Get-Location) "infra\VERSION")
)

foreach ($path in $searchPaths) {
    if (Test-Path $path) {
        $version = "v$((Get-Content $path -TotalCount 1).Trim())"
        break
    }
}

$xaml = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="SmartSafe AI Launcher" Height="450" Width="400" 
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        WindowStartupLocation="CenterScreen" Topmost="True">
    <Border CornerRadius="20" Background="#1A1A1A" BorderBrush="#333" BorderThickness="1">
        <Grid>
            <Grid.RowDefinitions>
                <RowDefinition Height="Auto"/>
                <RowDefinition Height="*"/>
                <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>
            
            <StackPanel Grid.Row="0" Margin="0,40,0,20">
                <TextBlock Text="SmartSafe AI" Foreground="White" FontSize="32" FontWeight="Bold" HorizontalAlignment="Center">
                    <TextBlock.Effect>
                        <DropShadowEffect Color="#00FFFF" BlurRadius="15" ShadowDepth="0"/>
                    </TextBlock.Effect>
                </TextBlock>
                <TextBlock Text="Geli$($s_kucuk)mi$($s_kucuk) $($I_noktali)SG Tespit Sistemi" Foreground="#888" FontSize="14" HorizontalAlignment="Center" Margin="0,5,0,0"/>
            </StackPanel>

            <StackPanel Grid.Row="1" VerticalAlignment="Center" Margin="40,0">
                <TextBlock Name="StatusText" Text="Ba$($s_kucuk)lat&#305;l&#305;yor..." Foreground="#EEE" FontSize="16" HorizontalAlignment="Left" Margin="0,0,0,10"/>
                <ProgressBar Name="Progress" Height="6" Background="#333" Foreground="#00FFFF" IsIndeterminate="True" BorderThickness="0" Margin="0,0,0,20">
                    <ProgressBar.Clip>
                        <RectangleGeometry Rect="0,0,320,6" RadiusX="3" RadiusY="3" />
                    </ProgressBar.Clip>
                </ProgressBar>
                <TextBlock Name="SubStatusText" Text="Sistem kontrolleri yap&#305;l&#305;yor..." Foreground="#666" FontSize="12" HorizontalAlignment="Left"/>
            </StackPanel>

            <TextBlock Grid.Row="2" Text="$version Production" Foreground="#444" FontSize="10" HorizontalAlignment="Center" Margin="0,0,0,20"/>
        </Grid>
    </Border>
</Window>
"@

# Bağımlılıkları tamamen sessizce yükle
$null = Add-Type -AssemblyName PresentationFramework
$null = Add-Type -AssemblyName System.Windows.Forms

$reader = [System.Xml.XmlReader]::Create([System.IO.StringReader]::new($xaml))
$Window = [System.Windows.Markup.XamlReader]::Load($reader)

$StatusText = $Window.FindName("StatusText")
$SubStatusText = $Window.FindName("SubStatusText")

function Update-Status($main, $sub) {
    $StatusText.Text = $main
    $SubStatusText.Text = $sub
    $null = [System.Windows.Forms.Application]::DoEvents()
}

function Check-Docker {
    try {
        $check = Get-Command "docker" -ErrorAction SilentlyContinue
        if ($check) {
            # Docker kurulu, çalışıyor mu?
            Update-Status "Docker Kontrol Ediliyor..." "Ba$($g_yumusak)lant$($i_noktasiz) sorgulan$($i_noktasiz)yor..."
            $daemon = docker info --format '{{.ID}}' 2>$null
            if (-not $daemon) {
                Update-Status "Docker Ba$($s_kucuk)lat&#305;l&#305;yor..." "Docker Desktop aç&#305;l&#305;yor, lütfen bekleyin..."
                Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -WindowStyle Hidden
                # Daemon'un gelmesi için biraz bekle
                $waitCount = 0
                while (-not (docker info 2>$null) -and $waitCount -lt 30) {
                    Start-Sleep -Seconds 2
                    $waitCount++
                    [System.Windows.Forms.Application]::DoEvents()
                }
            }
            return $true 
        }
    } catch {}

    Update-Status "Docker Bulunamad$($i_noktasiz)!" "Eksik bile$($s_kucuk)enler indiriliyor..."
    $installerPath = "$env:TEMP\DockerDesktopInstaller.exe"
    $url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    
    try {
        $webClient = New-Object System.Net.WebClient
        $webClient.DownloadFile($url, $installerPath)
        Update-Status "Docker Kuruluyor..." "Bu i$($s_kucuk)lem 3-5 dakika s$($u_kucuk)rebilir..."
        $null = Start-Process -FilePath $installerPath -ArgumentList "install", "--quiet", "--accept-license", "--install-privileged-helper" -Wait
        
        Update-Status "Docker Ba$($s_kucuk)lat$($i_noktali)l$($i_noktasiz)yor..." "Sistem servisi haz$($i_noktasiz)rlan$($i_noktasiz)yor..."
        Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe" -WindowStyle Hidden
        Start-Sleep -Seconds 15
    } catch {
        return $false
    }
    return $true
}

function Get-FreePort($startPort) {
    $port = $startPort
    while ($port -lt $startPort + 10) {
        $occupied = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if (-not $occupied) { return $port }
        $port++
    }
    return $startPort
}

$Window.Show()
[System.Windows.Forms.Application]::DoEvents()

# Boş portu bul ve Docker'a aktar
Update-Status "Port Kontrol Ediliyor..." "Uygun ba$($g_yumusak)lant$($i_noktasiz) noktas$($i_noktasiz) aran$($i_noktasiz)yor..."
$WEB_PORT = Get-FreePort 8088
$env:WEB_PORT = $WEB_PORT
$baseUrl = "http://localhost:$WEB_PORT"

if (-not (Check-Docker)) {
    Update-Status "HATA!" "Docker kurulumu ba$($s_kucuk)ar$($i_noktasiz)s$($i_noktasiz)z oldu."
    Start-Sleep -Seconds 5
    $Window.Close()
    exit
}

# Ad$($i_noktasiz)mlar
Update-Status "G$($u_kucuk)ncellemeler Denetleniyor..." "Bulut senkronizasyonu yap$($i_noktasiz)l$($i_noktasiz)yor..."
try { $null = Start-Process "docker" -ArgumentList "compose pull --quiet" -WindowStyle Hidden -Wait } catch {}

Update-Status "Konteynerler Haz$($i_noktasiz)rlan$($i_noktasiz)yor..." "Servisler aya$($g_yumusak)a kald$($i_noktasiz)r$($i_noktasiz)l$($i_noktasiz)yor..."
$null = Start-Process "docker" -ArgumentList "compose up -d --remove-orphans" -WindowStyle Hidden -Wait

Update-Status "Sistem Ba$($s_kucuk)lat$($i_noktali)l$($i_noktasiz)yor..." "Veritaban$($i_noktasiz) ve AI Motoru bekleniyor..."
$max_retries = 120 # 2 dakika limit
$count = 0
$ready = $false

while ($count -lt $max_retries) {
    try {
        # Dinamik portu kontrol et
        $response = Invoke-WebRequest -Uri $baseUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Ignore
        if ($response -and $response.StatusCode -eq 200) {
            $ready = $true
            break
        }
        Update-Status "Sistem Ba$($s_kucuk)lat$($i_noktali)l$($i_noktasiz)yor..." "Haz$($i_noktasiz)r olmas$($i_noktasiz) bekleniyor ($($count)s)..."
    } catch { }
    $count += 2
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Seconds 2
}

if ($ready) {
    Update-Status "Haz$($i_noktasiz)r!" "SmartSafe AI aç$($i_noktasiz)l$($i_noktasiz)yor..."
    if ($WEB_PORT -ne 8088) {
        Update-Status "Haz$($i_noktasiz)r!" "Not: Port çak$($i_noktasiz)$($s_kucuk)mas$($i_noktasiz) nedeniyle $WEB_PORT kullan$($i_noktasiz)l$($i_noktasiz)yor."
        Start-Sleep -Seconds 2
    }
    
    Start-Sleep -Seconds 1
    if (Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe") {
        Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--app=$baseUrl", "--start-maximized"
    } elseif (Test-Path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe") {
        Start-Process "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -ArgumentList "--app=$baseUrl", "--start-maximized"
    } else {
        Start-Process $baseUrl
    }
} else {
    Update-Status "Zaman A$($s_kucuk)$($i_noktasiz)m$($i_noktasiz)!" "Sistem beklenenden yava$($s_kucuk) aç$($i_noktasiz)l$($i_noktasiz)yor. L$($u_kucuk)tfen birazdan manuel deneyin."
    Start-Sleep -Seconds 5
}

$Window.Close()
