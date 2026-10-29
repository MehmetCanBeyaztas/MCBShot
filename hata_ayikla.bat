@echo off
rem Uygulamayi siyah pencerede calistirir; hata olursa mesaji burada gorursunuz.
cd /d "%~dp0"
".venv\Scripts\python.exe" run.py
pause
