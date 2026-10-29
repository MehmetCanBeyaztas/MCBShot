"""Geçmiş, sonradan düzenleme, galeri araması ve OCR."""
import os, sys, shutil, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-smoke_history_ocr")
shutil.rmtree(out, ignore_errors=True)
os.makedirs(out, exist_ok=True)

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent, QColor, QImage, QPainter, QFont
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)

from mcbshot import capture, overlay, ocr
from mcbshot.history import HistoryStore
from mcbshot.settings import Settings
from mcbshot.editor import window as ewin
from mcbshot.gallery import GalleryWindow

def wait(cond, timeout=15):
    t = time.time()
    while not cond() and time.time() - t < timeout:
        app.processEvents(); time.sleep(0.02)
    return cond()

store = HistoryStore(os.path.join(out, "hist"))
settings = Settings(os.path.join(out, "s.json")); settings.set("save_dir", os.path.join(out, "saved"))

# ---- 1) yakalama oturumu: çiz, kopyala -> geçmişe eklenmeli
shots = capture.capture_all()
sess = overlay.CaptureSession(shots, settings, store)
recorded = []
sess.recorded.connect(lambda i, img: recorded.append(i))
ov = sess.overlays[0]
ov.show(); app.processEvents()
vp = ov.viewport()
L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
def mouse(t, x, y):
    p = QPointF(x, y)
    QApplication.sendEvent(vp, QMouseEvent(t, p, vp.mapToGlobal(p), L if t != QEvent.Type.MouseMove else NB,
                                           NB if t == QEvent.Type.MouseButtonRelease else L, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
def drag(x1, y1, x2, y2, n=5):
    mouse(QEvent.Type.MouseButtonPress, x1, y1)
    for i in range(1, n + 1): mouse(QEvent.Type.MouseMove, x1 + (x2-x1)*i/n, y1 + (y2-y1)*i/n)
    mouse(QEvent.Type.MouseButtonRelease, x2, y2)
drag(300, 200, 900, 600)
ov.set_tool("arrow"); drag(350, 250, 550, 350)
ov.set_tool("text"); drag(600, 400, 600, 400, 1)
for ch in "Not: öğe": QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))
app.processEvents()
ov.copyRequested.emit(ov)
wait(lambda: recorded)
print("recorded:", recorded)
e = store.get(recorded[0])
print("entry", e.width, e.height, "scale", e.scale, "annotations:", [(a["type"], a["pos"]) for a in e.annotations])
print("files:", store.original_path(e.id).exists(), store.thumb_path(e.id).exists())

# ---- 2) yazılı sentetik görüntü -> geçmiş -> düzenleyicide OCR
img = QImage(1000, 260, QImage.Format.Format_RGB32); img.fill(QColor("white"))
p = QPainter(img); f = QFont("Segoe UI"); f.setPixelSize(42); p.setFont(f); p.setPen(QColor("black"))
p.drawText(30, 90, "Fatura numarası: TR-2026-0458"); p.drawText(30, 190, "Toplam tutar: 1.250,00 ₺ ödendi"); p.end()
eid = store.add(img, [], img, 1.0)
entry = store.get(eid)
ewin.OcrTextDialog.exec = lambda self: 0
w = ewin.EditorWindow(store, entry, settings)
w.show(); app.processEvents()
w.copy_text()
wait(lambda: "kopyalandı" in w.status.text() or "bulunamadı" in w.status.text())
print("editor status:", w.status.text())
print("clipboard:", repr(QGuiApplication.clipboard().text()))
print("ocr stored:", repr(store.get(eid).ocr_text))

# ---- 3) düzenleyicide sonradan değişiklik: kayıtlı oku taşı, kapat -> JSON güncellenmeli
w2 = ewin.EditorWindow(store, store.get(recorded[0]), settings)
w2.show(); app.processEvents()
arrow = [a for a in w2.canvas.annotations() if a.kind == "arrow"][0]
before = arrow.state()
arrow.setSelected(True)
w2.canvas.set_color(QColor("#34c759"))
print("dirty:", not w2.canvas.undo_stack.isClean(), "title:", w2.windowTitle())
w2.grab().save(os.path.join(out, "editor.png"))
w2.close(); app.processEvents()
after = [a for a in store.get(recorded[0]).annotations if a["type"] == "arrow"][0]
print("arrow color", before["color"], "->", after["color"])

# ---- 4) galeri: arama + silme
g = GalleryWindow(store, settings)
g.show(); app.processEvents()
print("gallery items:", g.list.count())
for q in ["fatura", "FATURA", "ödendi", "öğe", time.strftime("%d.%m.%Y"), "yokboyle"]:
    g.search.setText(q); app.processEvents()
    print(f"  search {q!r}:", g.count_label.text())
g.search.setText("")
g.grab().save(os.path.join(out, "gallery.png"))
store.delete(eid); app.processEvents(); time.sleep(0.3); app.processEvents()
print("after delete:", [x.id for x in store.entries()], "file gone:", not store.original_path(eid).exists())

# ---- 5) overlay OCR yolu
got = []
sess2 = overlay.CaptureSession(capture.capture_all(), settings, store)
sess2.ocrRequested.connect(lambda im, i: got.append((im.size(), i)))
ov2 = sess2.overlays[0]; ov2.show(); app.processEvents()
ov2.select_all(); ov2.ocrRequested.emit(ov2); app.processEvents()
print("overlay ocr emitted:", got, "closed", sess2._closed)
r = ocr.recognize(QImage(os.path.join(out, "gallery.png")))
print("ocr of gallery screenshot (first 80):", repr(r.text[:80]), r.language, r.fallback)
print("OK")
