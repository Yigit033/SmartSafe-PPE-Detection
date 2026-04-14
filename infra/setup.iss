; SmartSafe AI - Windows Production Installer
[Setup]
AppId={{5F7C0D0E-7B9E-4C4E-8B0E-7C1C2C3C4C5C}
AppName=SmartSafe AI
AppVersion=0.4.6
DefaultDirName={sd}\SmartSafe AI
DefaultGroupName=SmartSafe AI
OutputDir=..\landing\public\download
OutputBaseFilename=SmartSafe-AI-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "docker-compose.prod.yml"; DestDir: "{app}"; DestName: "docker-compose.yml"; Flags: ignoreversion
Source: "nginx\*"; DestDir: "{app}\nginx"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "scripts\launcher.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "scripts\baslat.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Ana kisayol - Terminalsiz baslatma
Name: "{group}\SmartSafe AI"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\scripts\launcher.ps1"""; WorkingDir: "{app}"; IconFilename: "{app}\nginx\ssl\favicon.ico"
Name: "{commondesktop}\SmartSafe AI"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\scripts\launcher.ps1"""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\nginx\ssl\favicon.ico"

[Run]
; Kurulum sonunda terminalsiz baslat
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\scripts\launcher.ps1"""; WorkingDir: "{app}"; Description: "Uygulamayı Şimdi Başlat"; Flags: postinstall nowait skipifsilent
