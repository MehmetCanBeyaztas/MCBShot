@echo off
cd /d "%~dp0"
echo.
echo === MCBShot kurulumu ===
echo.

if exist ".venv\Scripts\python.exe" goto install

echo Sanal ortam (.venv) olusturuluyor...
py -3.12 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" python -m venv .venv 2>nul
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo HATA: Python bulunamadi. README dosyasindaki 1. adimi uygulayin.
    pause
    exit /b 1
)

:install
echo Gerekli paketler yukleniyor (birkac dakika surebilir)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo HATA: Paketler yuklenemedi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
)
echo.
echo Kurulum tamam! Simdi baslat.bat dosyasina cift tiklayabilirsiniz.
pause
