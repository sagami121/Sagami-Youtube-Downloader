[Setup]
AppId={{D6C8E8C6-9E50-4F2E-A8E0-7C34A3F6D1B2}}
AppName=Sagami Youtube Downloader
AppVersion={{APP_VERSION}}
AppPublisher=sagami121
AppPublisherURL=https://github.com/sagami121/Sagami-Youtube-Downloader
DefaultDirName={autopf}\Sagami Youtube Downloader
DefaultGroupName=Sagami Youtube Downloader
OutputBaseFilename=Sagami Youtube Downloader_v{{APP_VERSION}}_Setup
OutputDir=.
UninstallDisplayIcon={app}\Sagami Youtube Downloader.exe
CreateUninstallRegKey=yes
DisableDirPage=no
UsePreviousAppDir=no
PrivilegesRequired=admin
UsedUserAreasWarning=no
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加オプション:"; Flags: unchecked

[Languages]
Name: "ja"; MessagesFile: "compiler:Languages\Japanese.isl"

[Files]
Source: "dist-package\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Sagami Youtube Downloader"; Filename: "{app}\Sagami Youtube Downloader.exe"
Name: "{autodesktop}\Sagami Youtube Downloader"; Filename: "{app}\Sagami Youtube Downloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Sagami Youtube Downloader.exe"; Description: "Sagami Youtube Downloader を起動"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\*"
Type: dirifempty; Name: "{app}"
Type: filesandordirs; Name: "{userappdata}\SagamiYoutubeDownloader\*"
Type: dirifempty; Name: "{userappdata}\SagamiYoutubeDownloader"
