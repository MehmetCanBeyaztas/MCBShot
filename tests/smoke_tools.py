"""Düzenleme araçları: her araçla çizim, Türkçe yazı, geri al/ileri al, taşıma, boyutlandırma, silme."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-smoke_tools")
os.makedirs(out, exist_ok=True)

from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent, QColor
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)

from mcbshot import capture, overlay
from mcbshot.editor.items import item_from_state
from mcbshot.settings import Settings

shots = capture.capture_all()
sess = overlay.CaptureSession(shots, Settings(os.path.join(out, "s.json")))
ov = sess.overlays[0]
ov.show(); ov.activateWindow(); app.processEvents()
vp = ov.viewport()
NB = Qt.MouseButton.NoButton; L = Qt.MouseButton.LeftButton

def mouse(t, x, y, btn=L, mods=Qt.KeyboardModifier.NoModifier):
    p = QPointF(x, y)
    buttons = NB if t == QEvent.Type.MouseButtonRelease else (btn if t != QEvent.Type.MouseMove or btn != NB else NB)
    ev = QMouseEvent(t, p, vp.mapToGlobal(p), btn if t != QEvent.Type.MouseMove else NB, buttons, mods)
    QApplication.sendEvent(vp, ev); app.processEvents()

def drag(x1, y1, x2, y2, steps=6, mods=Qt.KeyboardModifier.NoModifier):
    mouse(QEvent.Type.MouseButtonPress, x1, y1, mods=mods)
    for i in range(1, steps + 1):
        mouse(QEvent.Type.MouseMove, x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps, L, mods)
    mouse(QEvent.Type.MouseButtonRelease, x2, y2, mods=mods)

def click(x, y): drag(x, y, x, y, steps=1)

def key(k, text="", mods=Qt.KeyboardModifier.NoModifier):
    QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, k, mods, text)); app.processEvents()

drag(200, 150, 900, 600)
print("mode", ov.mode, "psel", ov.psel, "bars", ov.tool_panel.isVisible(), ov.action_bar.isVisible())

ov.set_tool("arrow"); drag(250, 200, 450, 300)
ov.set_tool("rect"); drag(500, 200, 650, 300)
ov.set_tool("ellipse"); drag(680, 200, 850, 300)
ov.set_tool("pen"); drag(250, 350, 400, 420, steps=12)
ov.set_color(QColor("#007aff"))
ov.set_tool("highlighter"); drag(250, 450, 500, 450)
ov.set_tool("step"); click(560, 380); click(620, 380); click(680, 380)
ov.set_tool("blur"); drag(260, 480, 420, 560)
ov.set_tool("pixelate"); drag(440, 480, 600, 560)
ov.set_tool("text"); click(650, 470)
for ch in "Çağrı şöyle: ĞÜŞİÖÇ ığüşöç":
    key(0, ch)
key(Qt.Key.Key_Escape)
app.processEvents()
print("annotations:", [a.kind for a in ov.annotations()])
print("undo count", ov.undo_stack.count(), [ov.undo_stack.command(i).text() for i in range(ov.undo_stack.count())])
ov.selected_image().save(os.path.join(out, "render_all.png"))
ov.grab().save(os.path.join(out, "overlay_editing.png"))

# geri al / ileri al
n = len(ov.annotations())
key(Qt.Key.Key_Z, mods=Qt.KeyboardModifier.ControlModifier)
print("after undo", len(ov.annotations()), "(was", n, ")")
key(Qt.Key.Key_Y, mods=Qt.KeyboardModifier.ControlModifier)
print("after redo", len(ov.annotations()))

# seç aracıyla dikdörtgeni taşı, sonra geri al
ov.set_tool("select")
rect_item = [a for a in ov.annotations() if a.kind == "rect"][0]
before = rect_item.pos()
drag(500, 250, 560, 330)
print("rect moved", before, "->", rect_item.pos(), "selected", rect_item.isSelected())
key(Qt.Key.Key_Z, mods=Qt.KeyboardModifier.ControlModifier)
print("rect after undo", rect_item.pos())

# tutamaçla boyutlandır: seç, sağ alt köşeyi sürükle
click(500, 250)
br = ov.view_pos(rect_item.handles()["br"])
drag(br.x(), br.y(), br.x() + 40, br.y() + 40)
print("rect resized", rect_item.rect)

# sil
key(Qt.Key.Key_Delete)
print("after delete", [a.kind for a in ov.annotations()])

# state -> yeni nesne (JSON gidiş-dönüş)
states = [a.state() for a in ov.annotations()]
clones = [item_from_state(s, ov.base_image).state() for s in states]
print("state roundtrip ok:", states == clones)
text_state = [s for s in states if s["type"] == "text"]
print("text:", text_state[0]["text"] if text_state else None)

# seçimi taşı (seç aracı, boş alan)
ov._scene.clearSelection()
old = Qt
p0 = ov.psel.topLeft()
drag(880, 580, 890, 590)
print("selection moved", p0, "->", ov.psel.topLeft())
print("OK")

