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
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayIcon={app}\nginx\ssl\favicon.ico
CloseApplications=force
RestartApplications=no

[InstallDelete]
; Kurulumdan önce eski betikleri temizle ki çakışma olmasın
Type: filesandordirs; Name: "{app}\scripts\*"

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "docker-compose.prod.yml"; DestDir: "{app}"; DestName: "docker-compose.yml"; Flags: ignoreversion
Source: "nginx\*"; DestDir: "{app}\nginx"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "scripts\launch.vbs"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "scripts\launcher.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "scripts\baslat.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Ana kisayol - Sifir terminal (VBS uzerinden)
Name: "{group}\SmartSafe AI"; Filename: "wscript.exe"; Parameters: """{app}\scripts\launch.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\nginx\ssl\favicon.ico"
Name: "{commondesktop}\SmartSafe AI"; Filename: "wscript.exe"; Parameters: """{app}\scripts\launch.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon; IconFilename: "{app}\nginx\ssl\favicon.ico"

[Run]
; Kurulum sonunda terminalsiz baslat
Filename: "wscript.exe"; Parameters: """{app}\scripts\launch.vbs"""; WorkingDir: "{app}"; Description: "Uygulamayı Şimdi Başlat"; Flags: postinstall nowait skipifsilent
