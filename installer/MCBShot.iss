; MCBShot kurulum programı (Inno Setup 6)
; Doğrudan derlemeyin: proje klasöründeki setup_olustur.bat dosyasını çalıştırın.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "MCBShot"
#define AppExe "MCBShot.exe"

[Setup]
; AppId sürümler arasında DEĞİŞMEMELİ (güncellemeler aynı kurulumun üzerine yazılsın)
AppId={{8F3C6B2E-4D1A-4E7B-9C55-2B7A1E0D9F41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Yönetici izni istemeden kullanıcının kendi klasörüne kurar; istenirse "tüm kullanıcılar" seçilebilir
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=MCBShot-Setup-{#AppVersion}
SetupIconFile=..\assets\mcbshot.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 1809 ve sonrası (OCR ve ekran yakalama dışlama özelliği için)
MinVersion=10.0.17763
; Güncellerken çalışan MCBShot'u kapat
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Kurulum

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
turkish.AutoStart=Windows açılınca MCBShot'u başlat
english.AutoStart=Start MCBShot when Windows starts
turkish.LaunchApp=MCBShot'u şimdi başlat
english.LaunchApp=Launch MCBShot now
turkish.DeleteData=MCBShot'un geçmişi (ekran görüntüsü kopyaları) ve ayarları da silinsin mi?%n%nKendi klasörlerinize kaydettiğiniz ekran görüntüleri silinmez.
english.DeleteData=Also delete MCBShot's history (screenshot copies) and settings?%n%nScreenshots you saved to your own folders are not deleted.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"

[Files]
Source: "..\dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.tr.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Uygulamanın kendi "Windows ile başlat" ayarıyla aynı kayıt.
; Programın kendi güncellemesinde yazılmaz: kullanıcının Ayarlar'daki seçimi korunsun.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MCBShot"; ValueData: """{app}\{#AppExe}"""; Tasks: autostart; Check: not IsAppUpdate

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
; MCBShot kendini güncellediğinde (sessiz kurulum + /relaunch=1) kurulum bitince yeniden aç
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: IsAppUpdate

[UninstallRun]
; Kaldırmadan önce çalışan MCBShot'u kapat
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "CloseMCBShot"

[Code]
function IsAppUpdate: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:relaunch|0}') = '1');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'MCBShot');

  if CurUninstallStep = usPostUninstall then
  begin
    if (not UninstallSilent) and
       (MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
    begin
      DelTree(ExpandConstant('{userappdata}\MCBShot'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\MCBShot'), True, True, True);
    end;
  end;
end;
