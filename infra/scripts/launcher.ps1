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
            
            <!-- Header/Logo -->
            <StackPanel Grid.Row="0" Margin="0,40,0,20">
                <TextBlock Text="SmartSafe AI" Foreground="White" FontSize="32" FontWeight="Bold" HorizontalAlignment="Center">
                    <TextBlock.Effect>
                        <DropShadowEffect Color="#00FFFF" BlurRadius="15" ShadowDepth="0"/>
                    </TextBlock.Effect>
                </TextBlock>
                <TextBlock Text="Advanced PPE Detection" Foreground="#888" FontSize="14" HorizontalAlignment="Center" Margin="0,5,0,0"/>
            </StackPanel>

            <!-- Status -->
            <StackPanel Grid.Row="1" VerticalAlignment="Center" Margin="40,0">
                <TextBlock Name="StatusText" Text="Başlatılıyor..." Foreground="#EEE" FontSize="16" HorizontalAlignment="Left" Margin="0,0,0,10"/>
                <ProgressBar Name="Progress" Height="6" Background="#333" Foreground="#00FFFF" IsIndeterminate="True" BorderThickness="0" Margin="0,0,0,20">
                    <ProgressBar.Clip>
                        <RectangleGeometry Rect="0,0,320,6" RadiusX="3" RadiusY="3" />
                    </ProgressBar.Clip>
                </ProgressBar>
                <TextBlock Name="SubStatusText" Text="Sistem kontrolleri yapılıyor..." Foreground="#666" FontSize="12" HorizontalAlignment="Left"/>
            </StackPanel>

            <!-- Footer -->
            <TextBlock Grid.Row="2" Text="v0.4.6 Production Release" Foreground="#444" FontSize="10" HorizontalAlignment="Center" Margin="0,0,0,20"/>
        </Grid>
    </Border>
</Window>
"@

# WPF Yukle
Add-Type -AssemblyName PresentationFramework
$reader = [System.Xml.XmlReader]::Create([System.IO.StringReader]::new($xaml))
$Window = [System.Windows.Markup.XamlReader]::Load($reader)

# Elementleri bul
$StatusText = $Window.FindName("StatusText")
$SubStatusText = $Window.FindName("SubStatusText")
$Progress = $Window.FindName("Progress")

# Arka plan islemlerini baslat
$Window.Show()

function Update-Status($main, $sub) {
    $StatusText.Text = $main
    $SubStatusText.Text = $sub
    [System.Windows.Forms.Application]::DoEvents()
}

# 1. Guncelleme Kontrolu
Update-Status "Güncellemeler Denetleniyor..." "Docker Hub üzerinden son sürüm kontrol ediliyor..."
Start-Process "docker" -ArgumentList "compose pull --quiet" -WindowStyle Hidden -Wait

# 2. Baslatma
Update-Status "Sistem Başlatılıyor..." "Konteynerlar optimize ediliyor..."
Start-Process "docker" -ArgumentList "compose up -d" -WindowStyle Hidden -Wait

# 3. Hazirlik Kontrolu (Postgres/Backend bekleyelim)
Update-Status "Ağ Bağlantısı Bekleniyor..." "Veritabanı ve AI motoru el sıkışıyor..."
$max_retries = 30
$count = 0
while ($count -lt $max_retries) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8088" -Method Head -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { break }
    } catch {}
    $count++
    Start-Sleep -Seconds 1
}

# 4. Uygulamayi Pencere Olarak Ac
Update-Status "Arayüz Yükleniyor..." "SmartSafe AI Desktop açılıyor..."
Start-Sleep -Seconds 1

# Edge'i "App" modunda ac ve terminali gizle
Start-Process "msedge" -ArgumentList "--app=http://localhost:8088", "--window-size=1280,800", "--window-name=SmartSafeAI" -WindowStyle Hidden

$Window.Close()
