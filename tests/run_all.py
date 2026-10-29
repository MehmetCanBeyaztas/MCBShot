"""Bütün otomatik testleri sırayla çalıştırır ve özet verir.

Kullanım (proje klasöründe):   .venv\\Scripts\\python.exe tests\\run_all.py

Notlar:
- Testler gerçek ekranı kullanır: çalışırken bilgisayara dokunmayın, ekran kilitli olmasın.
- smoke_scroll gerçek fare tekerleği gönderir; smoke_browser_scroll Microsoft Edge açar (varsayılan olarak atlanır,
  çalıştırmak için:  run_all.py --edge).
- Çalışan bir MCBShot varsa smoke_app kısayol çakışması uyarısı verir; bu beklenen bir durumdur.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = [
    ("smoke_tools.py", []),
    ("smoke_delete.py", []),
    ("smoke_history_ocr.py", []),
    ("smoke_editor.py", []),
    ("smoke_settings.py", []),
    ("smoke_multimonitor.py", []),
    ("smoke_scroll.py", ["3000", "60", "40"]),
    ("smoke_app.py", []),
]
if "--edge" in sys.argv:
    TESTS.append(("smoke_browser_scroll.py", []))

failed = []
for name, args in TESTS:
    start = time.time()
    proc = subprocess.run([sys.executable, os.path.join(HERE, name), *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    last = (proc.stdout.strip().splitlines() or [""])[-1]
    ok = proc.returncode == 0 and last == "OK"
    print(f"{'GEÇTİ ' if ok else 'HATA  '} {name:28s} {time.time() - start:5.1f} sn")
    if not ok:
        failed.append(name)
        print("   çıkış kodu:", proc.returncode)
        print("   " + "\n   ".join((proc.stdout + proc.stderr).strip().splitlines()[-15:]))

print()
print("Sonuç:", "hepsi geçti" if not failed else f"{len(failed)} test başarısız: {', '.join(failed)}")
sys.exit(1 if failed else 0)
