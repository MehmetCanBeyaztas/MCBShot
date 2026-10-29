@echo off
rem MCBShot kurulum dosyasini (setup) olusturur.
rem Sonuc: installer\Output\MCBShot-Setup-<surum>.exe
rem Gerekenler: kurulum.bat calistirilmis olmali + Inno Setup 6 (https://jrsoftware.org/isdl.php)
rem Kullanim: setup_olustur.bat            (sonunda bekler)
rem           setup_olustur.bat /nopause   (GitHub Actions kullanir)
cd /d "%~dp0"
set NOPAUSE=
if /i "%~1"=="/nopause" set NOPAUSE=1

set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo HATA: Inno Setup 6 bulunamadi. Kurmak icin:  winget install JRSoftware.InnoSetup
    if not defined NOPAUSE pause
    exit /b 1
)

echo 1/2  Program paketleniyor...
call "%~dp0paketle.bat" /nopause
if errorlevel 1 goto error

for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" mcbshot\__init__.py') do set "VERSION=%%v"
set "VERSION=%VERSION: =%"
set VERSION=%VERSION:"=%
echo 2/2  Kurulum dosyasi olusturuluyor (surum %VERSION%)...
"%ISCC%" /Q "/DAppVersion=%VERSION%" installer\MCBShot.iss
if errorlevel 1 goto error
echo.
echo Tamam! Kurulum dosyasi: %~dp0installer\Output\MCBShot-Setup-%VERSION%.exe
if not defined NOPAUSE pause
exit /b 0

:error
echo.
echo HATA: Kurulum dosyasi olusturulamadi. Yukaridaki mesajlara bakin.
if not defined NOPAUSE pause
exit /b 1
