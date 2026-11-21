[Setup]
AppId={{B1E3A2C4-5D6F-4A7B-8C9D-0E1F2A3B4C5D}
AppName=GH Downloader
AppVersion=1.2.0
DefaultDirName={autopf}\GH Downloader
DefaultGroupName=GH Downloader
OutputBaseFilename=GH Downloader-1.2.0-Setup
ArchitecturesInstallIn64BitMode=x64
SetupIconFile=icon.ico
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Files]
Source: "C:\Users\彭程\Desktop\gh-release-helper\dist\GH Downloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{autoprograms}\GH Downloader"; Filename: "{app}\GH Downloader.exe"; IconFilename: "icon.ico"
Name: "{autodesktop}\GH Downloader"; Filename: "{app}\GH Downloader.exe"; IconFilename: "icon.ico"

[Run]
Filename: "{app}\GH Downloader.exe"; Flags: postinstall nowait skipifsilent
