"""Uygulama simgesini (kodla çizilen) assets/mcbshot.ico dosyasına yazar. paketle.bat kullanır."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv)
from mcbshot import icons

os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
path = os.path.join(ROOT, "assets", "mcbshot.ico")
pixmap = icons.app_icon().pixmap(QSize(256, 256))
if not pixmap.toImage().save(path, "ICO"):
    raise SystemExit("Simge yazılamadı")
print("Simge:", path)
