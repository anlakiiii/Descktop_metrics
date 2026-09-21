#define MyAppName "Desktop Metrics"
#define MyAppVersion "1.8.1"
#define MyAppPublisher "Desktop Metrics"
#define MyAppExeName "DesktopMetrics.exe"
#define MyAppUserModelId "DesktopMetrics.DesktopMetrics.1"

[Setup]
AppId={{F11D1C3F-F101-4ED8-8C7D-105C0CC52B45}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\Desktop Metrics
DefaultGroupName=Desktop Metrics
DisableProgramGroupPage=yes
AllowNoIcons=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=DesktopMetrics-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\desktop_metrics.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=DesktopMetrics.DesktopMetrics.AppMutex
VersionInfoVersion=1.8.1.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; Optional code signing. Configure an Inno Setup Sign Tool with this exact
; name, then uncomment both lines. Leaving them commented keeps unsigned
; personal builds working on PCs without a certificate.
; SignTool=DesktopMetricsSign
; SignedUninstaller=yes

[Tasks]
Name: "startup"; Description: "Start Desktop Metrics automatically when I sign in"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\DesktopMetrics\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Desktop Metrics"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelId}"
Name: "{autodesktop}\Desktop Metrics"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "{#MyAppUserModelId}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DesktopMetrics"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "DesktopMetrics"; Flags: deletevalue; Tasks: not startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Desktop Metrics"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
