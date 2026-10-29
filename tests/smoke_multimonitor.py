"""İki monitöre yayılan seçim testi."""
import ctypes, os, sys
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-span"); os.makedirs(out, exist_ok=True)
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot import capture, overlay
from mcbshot.settings import Settings

shots = capture.capture_all()
print("shots:", len(shots), [(s.physical, s.spans, s.dpr, s.screen_rects) for s in shots])
if not shots[0].spans:
    # Tek monitör (ya da ölçekleri farklı monitörler): yayılma yok, sadece her monitörün tam yakalandığını sına
    for s in shots:
        assert s.image.width() == s.physical.width() and s.image.height() == s.physical.height()
    print("Bağlı tek monitör var ya da ölçekler farklı: yayılan seçim testi atlandı.")
    print("OK")
    sys.exit(0)
sess = overlay.CaptureSession(shots, Settings(os.path.join(out, "s.json")))
sess.start(); app.processEvents()
ov = sess.overlays[0]
r = wintypes.RECT(); ctypes.windll.user32.GetWindowRect(int(ov.winId()), ctypes.byref(r))
print("native window:", (r.left, r.top, r.right - r.left, r.bottom - r.top), "qt geom:", ov.geometry(), "viewport:", ov.viewport().size())

vp = ov.viewport()
L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
def mouse(t, x, y):
    p = QPointF(x, y)
    QApplication.sendEvent(vp, QMouseEvent(t, p, vp.mapToGlobal(p), L if t != QEvent.Type.MouseMove else NB,
                                           NB if t == QEvent.Type.MouseButtonRelease else L, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
def drag(x1, y1, x2, y2, n=6):
    mouse(QEvent.Type.MouseButtonPress, x1, y1)
    for i in range(1, n + 1): mouse(QEvent.Type.MouseMove, x1 + (x2-x1)*i/n, y1 + (y2-y1)*i/n)
    mouse(QEvent.Type.MouseButtonRelease, x2, y2)

# Acer (sol, x 0..1919) -> Dell (sağ, x 1920..4479) arası
drag(1500, 300, 2400, 800)
print("span selection psel:", ov.psel, "global top-left:", ov.psel.topLeft() + shots[0].physical.topLeft())
print("action bar:", ov.action_bar.geometry(), "tool panel:", ov.tool_panel.geometry())
ov.set_tool("arrow"); drag(1600, 400, 2300, 700)
img = ov.selected_image()
print("rendered:", img.size())
img.save(os.path.join(out, "span_render.png"))
ov.grab().scaled(2240, 720).save(os.path.join(out, "span_overlay.png"))

# Acer'in altına (görünmeyen köşe) uzanan seçim: çubuklar görünen alanda kalmalı
ov.undo_stack.undo(); app.processEvents()
ov.reset_selection(); ov.set_tool("select")
drag(1000, 900, 1800, 1400)
ab, tp = ov.action_bar.geometry(), ov.tool_panel.geometry()
print("lower-left selection psel:", ov.psel, "action bar:", ab, "tool panel:", tp)
acer = ov._to_logical(shots[0].screen_rects[1]) if shots[0].spans else None
dell = ov._to_logical(shots[0].screen_rects[0]) if shots[0].spans else None
def visible(g): return any(sr.contains(QPointF(g.center())) for sr in (acer, dell))
print("bars on a visible screen:", visible(ab), visible(tp))

# Ctrl+A / Ctrl+Shift+A
ov._cursor_pos = QPointF(500, 500)
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)); app.processEvents()
print("Ctrl+A (cursor on Acer):", ov.psel)
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)); app.processEvents()
print("Ctrl+Shift+A:", ov.psel)
sess.close()
print("per-screen fallback:", [(s.physical, s.spans) for s in capture.capture_all(allow_span=False)])
print("OK")
