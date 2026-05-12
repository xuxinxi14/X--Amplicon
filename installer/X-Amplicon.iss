#define MyAppName "X-Amplicon"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "X-Amplicon"
#define MyAppURL "https://github.com/xuxinxi14/X--Amplicon"
#define MyAppExe "Start_X-Amplicon_WebUI.vbs"
#define MyAppIcon "X-Amplicon.ico"

[Setup]
AppId={{1A612B57-784B-4C02-932B-9FE19F7D4421}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\X-Amplicon
DefaultGroupName=X-Amplicon
DisableDirPage=no
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\X-Amplicon_win64\README_RELEASE_zh.md
OutputDir=..\dist\installer
OutputBaseFilename=X-Amplicon-Setup-v0.1.0
SetupIconFile={#MyAppIcon}
SetupLogging=yes
Compression=none
SolidCompression=no
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=X-Amplicon
UninstallDisplayIcon={app}\{#MyAppIcon}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=X-Amplicon Windows Web UI installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\X-Amplicon_win64.zip"; DestDir: "{tmp}"; DestName: "X-Amplicon_main.zip"; Flags: deleteafterinstall
Source: "install_payload.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "{#MyAppIcon}"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\seq"
Name: "{app}\work"

[Icons]
Name: "{autoprograms}\X-Amplicon Web UI"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIcon}"
Name: "{autodesktop}\X-Amplicon Web UI"; Filename: "{app}\{#MyAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppIcon}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{tmp}\install_payload.ps1"" -ZipPath ""{tmp}\X-Amplicon_main.zip"" -Destination ""{app}"""; StatusMsg: "Extracting bundled X-Amplicon runtime..."; Flags: runhidden
Filename: "{app}\{#MyAppExe}"; Description: "Launch X-Amplicon Web UI"; WorkingDir: "{app}"; Flags: postinstall skipifsilent nowait shellexec

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.xamplicon_webui"
Type: filesandordirs; Name: "{app}\run_logs"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
  if not IsWin64 then
  begin
    MsgBox('X-Amplicon bundles a 64-bit Python runtime and requires 64-bit Windows.', mbError, MB_OK);
    Result := False;
  end;
end;
