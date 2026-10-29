@echo off
rem MCBShot'u tek bir .exe dosyasi olarak paketler. Sonuc: dist\MCBShot.exe
rem Kullanim: paketle.bat            (sonunda bekler)
rem           paketle.bat /nopause   (setup_olustur.bat kullanir)
cd /d "%~dp0"
set NOPAUSE=
if /i "%~1"=="/nopause" set NOPAUSE=1
if not exist ".venv\Scripts\python.exe" (
    echo Once kurulum.bat dosyasini calistirin.
    if not defined NOPAUSE pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq MCBShot.exe" | find /I "MCBShot.exe" >nul
if not errorlevel 1 (
    echo Calisan MCBShot kapatiliyor...
    taskkill /F /IM MCBShot.exe >nul
    ping -n 3 127.0.0.1 >nul
)
echo PyInstaller kuruluyor...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto error
echo Simge hazirlaniyor...
".venv\Scripts\python.exe" tools\make_icon.py
if errorlevel 1 goto error
echo Paketleniyor (birkac dakika surebilir)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name MCBShot --icon assets\mcbshot.ico ^
    --collect-submodules winrt ^
    --exclude-module tkinter ^
    run.py
if errorlevel 1 goto error
if exist build rmdir /s /q build
echo.
echo Tamam! Dosya: %~dp0dist\MCBShot.exe
if not defined NOPAUSE pause
exit /b 0

:error
echo.
echo HATA: Paketleme basarisiz oldu. Yukaridaki mesajlara bakin.
if not defined NOPAUSE pause
exit /b 1
