"""Düzenleyici: yakınlaştırma ve kırpma testi."""
import os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-editor"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
from PySide6.QtCore import Qt, QPointF, QEvent, QRect
from PySide6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent, QColor, QImage, QPainter, QFont
from PySide6.QtWidgets import QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot.history import HistoryStore
from mcbshot.settings import Settings
from mcbshot.editor.window import EditorWindow
from mcbshot.editor.canvas import render_annotated
from mcbshot.editor.items import ArrowItem

store = HistoryStore(os.path.join(out, "hist"))
img = QImage(1600, 900, QImage.Format.Format_RGB32); img.fill(QColor("#dfe6ee"))
p = QPainter(img); f = QFont("Segoe UI"); f.setPixelSize(60); p.setFont(f)
p.fillRect(100, 100, 600, 300, QColor("#3a7bd5")); p.setPen(QColor("black")); p.drawText(900, 300, "Sağ taraf"); p.end()
arrow = ArrowItem(QColor("red"), 6, QPointF(0, 0), QPointF(300, 150)); arrow.setPos(150, 150)
eid = store.add(img, [arrow.state()], img, 1.0)
w = EditorWindow(store, store.get(eid), Settings(os.path.join(out, "s.json")))
w.resize(1000, 700); w.show(); app.processEvents()
c = w.canvas
print("initial zoom label:", w.zoom_label.text(), "fit_mode:", c.fit_mode)
QApplication.sendEvent(c, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)); app.processEvents()
print("Ctrl+1 ->", w.zoom_label.text(), "scrollbars visible:", c.horizontalScrollBar().isVisible())
QApplication.sendEvent(c, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)); app.processEvents()
print("Ctrl++ ->", w.zoom_label.text())
QApplication.sendEvent(c, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)); app.processEvents()
print("Ctrl+0 ->", w.zoom_label.text(), "fit_mode:", c.fit_mode)

# kırp: sol yarıyı tut
vp = c.viewport()
def mouse(t, pt, btn=Qt.MouseButton.LeftButton):
    QApplication.sendEvent(vp, QMouseEvent(t, pt, vp.mapToGlobal(pt), btn if t != QEvent.Type.MouseMove else Qt.MouseButton.NoButton,
                                           Qt.MouseButton.NoButton if t == QEvent.Type.MouseButtonRelease else btn, Qt.KeyboardModifier.NoModifier))
    app.processEvents()
w._crop_clicked(); app.processEvents()
print("crop mode:", c.crop_mode, "btn checked:", w.crop_btn.isChecked())
a, b = c.view_pos(QPointF(50, 50)), c.view_pos(QPointF(800, 600))
mouse(QEvent.Type.MouseButtonPress, a)
for i in range(1, 6): mouse(QEvent.Type.MouseMove, a + (b - a) * (i / 5))
mouse(QEvent.Type.MouseButtonRelease, b)
print("cropped:", c.edit_rect, "crop mode off:", not c.crop_mode, "title:", w.windowTitle())
w.grab().save(os.path.join(out, "editor_cropped.png"))
print("render size:", c.render_image().size())
c.undo_stack.undo(); app.processEvents()
print("undo crop ->", c.edit_rect)
c.undo_stack.redo(); app.processEvents()
w.close(); app.processEvents()
e = store.get(eid)
print("saved crop:", e.crop, "display size:", e.display_size())
print("gallery render:", render_annotated(store.original_image(eid), e.annotations, e.crop).size())
w2 = EditorWindow(store, e, Settings(os.path.join(out, "s.json"))); w2.show(); app.processEvents()
print("reopened crop:", w2.canvas.edit_rect)
w2._uncrop(); w2.close(); app.processEvents()
print("after uncrop saved:", store.get(eid).crop)
print("OK")
