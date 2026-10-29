"""Tepsi uygulamasının bağlantıları: ayarlar, gecikmeli yakalama, kaydırmalı yakalama -> geçmiş -> düzenleyici.
Gerçek geçmiş/ayarlar yerine geçici klasör kullanılır."""
import os, shutil, sys, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mcbs-app-")
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QGuiApplication, QImage, QColor
from PySide6.QtWidgets import QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
qapp = QApplication(sys.argv)
qapp.setQuitOnLastWindowClosed(False)

import mcbshot.app as appmod
import mcbshot.history as hist
from mcbshot.settings import Settings
hist.history_dir = lambda: __import__("pathlib").Path(tmp) / "history"
appmod.Settings = lambda: Settings(os.path.join(tmp, "settings.json"))
appmod.SettingsDialog.exec = lambda self: 0

def pump(sec):
    t = time.time()
    while time.time() - t < sec:
        qapp.processEvents(); time.sleep(0.01)

a = appmod.MCBShotApp(qapp)
print("menu:", [act.text().replace("\t", " | ") for act in a.menu.actions() if act.text()])
print("active hotkeys (exe çalıştığı için çakışma beklenir):", a.active_hotkeys)

a.show_settings(); print("settings dialog opened/closed ok")

a.settings.set("delay_seconds", 1)
a.start_delayed_capture(); print("delay timer active:", a._delay_timer.isActive())
pump(1.5); print("session after delay:", a._session is not None)
a._session.close(); pump(0.2)

a.start_scroll_capture(); pump(0.2)
print("scroll mode overlays:", [ov.scroll_mode for ov in a._session.overlays])
a._session.close(); pump(0.2)

# Kaydırma işinin kendisi test edildi; burada sadece sonucu: geçmiş + düzenleyici
img = QImage(800, 3000, QImage.Format.Format_RGB32); img.fill(QColor("#cde"))
a._scroll_dpr = 1.0
class FakeJob:
    def deleteLater(self): pass
a._scroll_job = FakeJob()
a._on_scroll_finished(img, "ok"); pump(0.3)
entries = a.history.entries()
print("history entries:", len(entries), entries[0].width, "x", entries[0].height if entries else None)
print("editor opened:", list(a._editors))
for w in list(a._editors.values()): w.close()
pump(0.3)
a.show_gallery(); pump(0.3); print("gallery items:", a._gallery.list.count()); a._gallery.close()
a.quit(); pump(0.2)
shutil.rmtree(tmp, ignore_errors=True)
print("OK")
