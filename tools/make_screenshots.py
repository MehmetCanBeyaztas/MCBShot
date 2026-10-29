"""README için tanıtım ekran görüntüleri üretir (docs/screenshots/).

Gerçek ekran KULLANILMAZ: içerik programla çizilen örnek bir "web sayfası"dır, böylece
kişisel bilgi görüntülere girmez. Çalışırken ekranda birkaç saniye pencereler açılıp kapanır.

Kullanım:  .venv\\Scripts\\python.exe tools\\make_screenshots.py
"""
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication

QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)

from mcbshot.capture import ScreenShot
from mcbshot.editor.items import ArrowItem, CensorItem, RectItem, StepItem, TextItem
from mcbshot.editor.window import EditorWindow
from mcbshot.gallery import GalleryWindow
from mcbshot.history import HistoryStore
from mcbshot.overlay import CaptureSession
from mcbshot.settings import Settings
from mcbshot.settings_window import SettingsDialog

TMP = tempfile.mkdtemp(prefix="mcbs-shots-")


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def font(px, bold=False):
    f = QFont("Segoe UI")
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def fake_page(w, h, s, title="Sipariş özeti", hue=210):
    """Örnek bir web sayfası (s = ölçek)."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillRect(0, 0, w, h, QColor("#f4f6f9"))
    p.fillRect(0, 0, w, int(64 * s), QColor.fromHsv(hue, 160, 120))
    p.setPen(QColor("white"))
    p.setFont(font(24 * s, True))
    p.drawText(int(32 * s), int(42 * s), "ÖrnekMağaza")
    p.setFont(font(15 * s))
    for i, item in enumerate(["Ürünler", "Kampanyalar", "Siparişlerim", "Yardım"]):
        p.drawText(int((330 + i * 130) * s), int(40 * s), item)
    card = QRectF(32 * s, 96 * s, w - 64 * s, h - 128 * s)
    p.setPen(QPen(QColor("#dde2ea"), 1))
    p.setBrush(QColor("white"))
    p.drawRoundedRect(card, 10 * s, 10 * s)
    x0, y = card.left() + 32 * s, card.top() + 56 * s
    p.setPen(QColor("#1d2733"))
    p.setFont(font(30 * s, True))
    p.drawText(QPointF(x0, y), title)
    rows = [("Sipariş no", "TR-2026-104583"), ("Tarih", "29.10.2026"), ("E-posta", "ornek.kisi@eposta.com"),
            ("Teslimat", "Atatürk Cad. No:12, Kadıköy / İstanbul"), ("Ödeme", "Kredi kartı •••• 4821")]
    p.setFont(font(18 * s))
    for i, (k, v) in enumerate(rows):
        yy = y + (60 + i * 46) * s
        p.setPen(QColor("#6b7685"))
        p.drawText(QPointF(x0, yy), k)
        p.setPen(QColor("#1d2733"))
        p.drawText(QPointF(x0 + 190 * s, yy), v)
    ty = y + 330 * s
    p.setPen(QPen(QColor("#e6e9ef"), 1))
    p.drawLine(QPointF(x0, ty - 34 * s), QPointF(card.right() - 32 * s, ty - 34 * s))
    p.setFont(font(18 * s))
    for i, (name, price) in enumerate([("Kablosuz kulaklık", "1.249,90 ₺"), ("USB-C şarj kablosu", "189,00 ₺"),
                                       ("Telefon kılıfı", "149,50 ₺")]):
        yy = ty + i * 44 * s
        p.setPen(QColor("#1d2733"))
        p.drawText(QPointF(x0, yy), name)
        p.drawText(QPointF(card.right() - 200 * s, yy), price)
    p.setFont(font(22 * s, True))
    p.drawText(QPointF(x0, ty + 160 * s), "Toplam")
    p.drawText(QPointF(card.right() - 200 * s, ty + 160 * s), "1.588,40 ₺")
    btn = QRectF(card.right() - 280 * s, ty + 200 * s, 240 * s, 52 * s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2f8cff"))
    p.drawRoundedRect(btn, 8 * s, 8 * s)
    p.setPen(QColor("white"))
    p.setFont(font(18 * s, True))
    p.drawText(btn, Qt.AlignmentFlag.AlignCenter, "Siparişi onayla")
    p.end()
    return img


def desktop(screen):
    """Örnek sayfanın bir tarayıcı penceresi gibi durduğu sahte masaüstü (fiziksel piksel)."""
    s = screen.devicePixelRatio()
    g = screen.geometry()
    w, h = round(g.width() * s), round(g.height() * s)
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0, QColor("#2b5876"))
    grad.setColorAt(1, QColor("#4e4376"))
    p.fillRect(0, 0, w, h, grad)
    win = QRect(int(w * 0.12), int(h * 0.08), int(w * 0.62), int(h * 0.8))
    p.fillRect(win.adjusted(0, 0, 0, -win.height() + int(44 * s)), QColor("#dfe3ea"))
    p.drawImage(win.topLeft() + QRect(0, int(44 * s), 0, 0).topLeft(),
                fake_page(win.width(), win.height() - int(44 * s), s))
    p.end()
    return img, win, s


# ---- 1) Seçim ekranı + düzenleme araçları ----
screen = QGuiApplication.primaryScreen()
image, win, s = desktop(screen)
shot = ScreenShot([screen], image, QRect(screen.geometry().topLeft(), image.size()), s,
                  [QRect(0, 0, image.width(), image.height())])
settings = Settings(os.path.join(TMP, "settings.json"))
sess = CaptureSession([shot], settings)
sess.start()
pump(0.5)
ov = sess.overlays[0]
sel = QRect(win.left() + int(20 * s), win.top() + int(150 * s), int(win.width() * 0.78), int(560 * s))
ov.psel = sel
ov.mode = ov.mode.__class__.SELECTED
ov._place_bars()
c = QPointF(sel.topLeft())
start = QPointF(sel.width() * 0.44, 170 * s)          # yazının solundan "Sipariş no" kutusuna
arrow = ArrowItem(QColor("#ff3b30"), 5 * s, QPointF(0, 0), QPointF(490 * s, 102 * s) - start)
arrow.setPos(c + start)
box = RectItem(QColor("#ff3b30"), 4 * s)
box.set_geom_rect(QRectF(0, 0, 440 * s, 52 * s))
box.setPos(c + QPointF(40 * s, 76 * s))
blur = CensorItem("blur", image, 9 * s)
blur.set_geom_rect(QRectF(0, 0, 330 * s, 40 * s))
blur.setPos(c + QPointF(240 * s, 166 * s))
pix = CensorItem("pixelate", image, 9 * s)
pix.set_geom_rect(QRectF(0, 0, 300 * s, 40 * s))
pix.setPos(c + QPointF(240 * s, 258 * s))
step1 = StepItem(QColor("#2f8cff"), 15 * s, 1)
step1.setPos(c + QPointF(20 * s, 102 * s))
step2 = StepItem(QColor("#2f8cff"), 15 * s, 2)
step2.setPos(c + QPointF(20 * s, 528 * s))
note = TextItem(QColor("#ff3b30"), 24 * s, "Sipariş numarasını kontrol et", "box")
note.setPos(c + QPointF(sel.width() * 0.45, 150 * s))
for it in (box, blur, pix, arrow, step1, step2, note):
    ov._add_new(it)
ov.set_tool("arrow")
ov.viewport().update()
pump(0.5)
grab = ov.grab()
dpr = grab.devicePixelRatio()
tp, ab = ov.tool_panel.geometry(), ov.action_bar.geometry()
area = ov._to_logical(sel).toAlignedRect().united(tp).united(ab).adjusted(-60, -60, 60, 60)
area = area.intersected(ov.rect())
crop = grab.copy(QRect(int(area.x() * dpr), int(area.y() * dpr), int(area.width() * dpr), int(area.height() * dpr)))
crop.save(os.path.join(OUT, "capture.png"))
rendered = ov.render_image()
sess.close()
pump(0.3)
print("capture.png", crop.size())

# ---- 2) Geçmiş galerisi ----
store = HistoryStore(os.path.join(TMP, "history"))
titles = ["Sipariş özeti", "Kargo takibi", "Fatura", "Hesap ayarları", "Kampanya", "Destek talebi"]
ids = []
for i, t in enumerate(titles):
    page = fake_page(1100, 760, 1.0, t, hue=(210 + i * 40) % 360)
    ids.append(store.add(page, [], page, 1.0))
store.set_ocr_text(ids[0], "Sipariş özeti TR-2026-104583")
gal = GalleryWindow(store, settings)
gal.resize(1080, 640)
gal.show()
pump(0.6)
gal.list.item(1).setSelected(True)
pump(0.2)
gal.grab().save(os.path.join(OUT, "gallery.png"))
gal.close()
print("gallery.png")

# ---- 3) Sonradan düzenleme penceresi ----
orig = fake_page(1100, 760, 1.0, "Fatura")
states = []
a = ArrowItem(QColor("#ff3b30"), 5, QPointF(0, 0), QPointF(140, -60)); a.setPos(560, 300); states.append(a.state())
r = RectItem(QColor("#34c759"), 4); r.set_geom_rect(QRectF(0, 0, 420, 52)); r.setPos(50, 590); states.append(r.state())
t = TextItem(QColor("white"), 22, "Toplamı kontrol et", "glow"); t.setPos(500, 600); states.append(t.state())
st = StepItem(QColor("#ff9500"), 14, 1); st.setPos(735, 215); states.append(st.state())
eid = store.add(orig, states, orig, 1.0)
ed = EditorWindow(store, store.get(eid), settings)
ed.resize(1100, 760)
ed.show()
pump(0.6)
ed.grab().save(os.path.join(OUT, "editor.png"))
ed.canvas.undo_stack.setClean()
ed.discard()
print("editor.png")

# ---- 4) Ayarlar ----
settings.set("save_dir", r"C:\Users\Kullanici\Pictures\MCBShot")   # gerçek kullanıcı adı görünmesin
dlg = SettingsDialog(settings, history_count=6)
dlg.show()
pump(0.4)
dlg.grab().save(os.path.join(OUT, "settings.png"))
tabs = dlg.findChild(type(dlg.layout().itemAt(0).widget()))
tabs.setCurrentIndex(1)
pump(0.3)
dlg.grab().save(os.path.join(OUT, "settings_hotkeys.png"))
dlg.close()
dlg.deleteLater()
print("settings.png")

store.close()
pump(0.3)
shutil.rmtree(TMP, ignore_errors=True)
print("Bitti:", OUT)
