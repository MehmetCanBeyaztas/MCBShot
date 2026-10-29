"""Nesne silme yolları: tıkla+Delete, çöp kutusu düğmesi, sağ tık menüsü, geri al."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QMenu
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot import capture, overlay
from mcbshot.settings import Settings

sess = overlay.CaptureSession(capture.capture_all(), Settings(os.path.join(os.environ["TEMP"], "mcbs-s4.json")))
ov = sess.overlays[0]; ov.show(); app.processEvents()
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
def click(x, y):
    mouse(QEvent.Type.MouseButtonPress, x, y); mouse(QEvent.Type.MouseButtonRelease, x, y)
def key(k): QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, k, Qt.KeyboardModifier.NoModifier)); app.processEvents()
kinds = lambda: [a.kind for a in ov.annotations()]
sel = lambda: [a.kind for a in ov.selected_annotations()]
trash = [b for b in ov.action_bar.findChildren(type(ov.action_bar.findChild(QApplication.instance().__class__) or object)) ] if False else None
from PySide6.QtWidgets import QToolButton
trash = [b for b in ov.action_bar.findChildren(QToolButton) if "sil" in b.toolTip().lower()][0]

drag(200, 150, 900, 600)
ov.set_tool("rect"); drag(300, 200, 500, 350)
ov.set_tool("arrow"); drag(550, 200, 750, 300)
ov.set_tool("step"); click(600, 450)
print("start:", kinds(), "trash enabled:", trash.isEnabled())

# ok aracı açıkken dikdörtgenin kenarına tıkla -> dikdörtgen seçilmeli, yeni çizim olmamalı
ov.set_tool("arrow"); click(300, 275)
print("arrow tool click on rect -> selected:", sel(), "kinds:", kinds(), "trash enabled:", trash.isEnabled())
key(Qt.Key.Key_Delete)
print("after Delete:", kinds())
key(Qt.Key.Key_Z) if False else QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)); app.processEvents()
print("after Ctrl+Z:", kinds())

# kalem aracıyla oka tıkla -> ok seçilmeli; çöp düğmesiyle sil
ov.set_tool("pen"); click(650, 250)
print("pen tool click on arrow -> selected:", sel())
trash.click(); app.processEvents()
print("after trash button:", kinds())

# kalemle boş yere tıklama hala nokta koymalı
click(820, 560)
print("pen click on empty:", kinds())

# adım aracıyla var olan adıma tıklama -> seçer, yeni adım eklemez
ov.set_tool("step"); click(600, 450)
print("step tool click on step -> selected:", sel(), "kinds:", kinds())
click(700, 450)
print("step tool click empty -> kinds:", kinds())

# sağ tık menüsü
QMenu.exec = lambda self, *a: [x for x in self.actions() if x.text().startswith("Sil")][0].trigger()
ov._scene.clearSelection()
r = ov.annotations()[0]
pos = ov.view_pos(r.sceneBoundingRect().center())
print("context menu on", r.kind, "->", ov.show_item_menu(pos), "kinds:", kinds())
print("OK")
