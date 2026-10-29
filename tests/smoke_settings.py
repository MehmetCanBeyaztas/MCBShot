"""5. aşama testi: ayarlar penceresi, Windows ile başlat, geçmiş temizliği, küçük eklemeler."""
import os, shutil, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-settings"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
from datetime import datetime, timedelta
from PySide6.QtCore import Qt, QPointF, QEvent
from PySide6.QtGui import QGuiApplication, QKeyEvent, QColor, QImage
from PySide6.QtWidgets import QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot import capture, overlay, settings as st
from mcbshot.settings_window import SettingsDialog, HotkeyEdit
from mcbshot.history import HistoryStore
from mcbshot.editor.items import TextItem
from mcbshot.editor.canvas import render_annotated

# ---- HotkeyEdit: tuş yakalama (klavye düzeninden bağımsız sanal tuş kodu ile)
e = HotkeyEdit()
def press(widget, key, vk, mods=Qt.KeyboardModifier.NoModifier, release=False):
    t = QEvent.Type.KeyRelease if release else QEvent.Type.KeyPress
    QApplication.sendEvent(widget, QKeyEvent(t, key, mods, 0, vk, 0, ""))
press(e, Qt.Key.Key_X, 0x58, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
print("Ctrl+Shift+X ->", e.hotkey, "| shown:", e.text())
press(e, Qt.Key.Key_Print, 0x2C, release=True)
print("Print (release) ->", e.hotkey, "| shown:", e.text())
press(e, Qt.Key.Key_A, 0x41)
print("plain A ignored ->", e.hotkey)
press(e, Qt.Key.Key_Backspace, 0x08)
print("Backspace clears ->", repr(e.hotkey))

# ---- Ayarlar penceresi
s = st.Settings(os.path.join(out, "settings.json"))
dlg = SettingsDialog(s, test_hotkey=lambda t: (t != "Ctrl+F12", 1409), history_count=7)
dlg.show(); app.processEvents()
dlg.grab().save(os.path.join(out, "dialog_general.png"))
dlg.findChild(type(dlg.findChildren(QApplication.instance().__class__)) if False else object)
dlg.delay.setValue(5); dlg.format.setCurrentIndex(dlg.format.findData("jpg")); dlg.quality.setValue(75)
dlg.template.setText("ekran_{tarih}"); dlg.keep_days.setValue(30); dlg.max_items.setValue(2)
dlg.save_dir.setText(os.path.join(out, "kayitlar"))
dlg.text_style.setCurrentIndex(dlg.text_style.findData("box"))
print("preview:", dlg.preview.text(), "quality enabled (jpg):", dlg.quality.isEnabled())
# çakışan kısayol reddedilmeli
dlg.hotkey_edits["history"].hotkey = "Print"
from PySide6.QtWidgets import QMessageBox
warnings = []
QMessageBox.warning = staticmethod(lambda *a: warnings.append(a[2]) or 0)
dlg.accept(); print("duplicate rejected:", bool(warnings), "| visible:", dlg.isVisible())
dlg.hotkey_edits["history"].hotkey = "Ctrl+F12"
dlg.accept(); print("taken hotkey rejected:", warnings[-1][:60] if len(warnings) > 1 else None)
dlg.hotkey_edits["history"].hotkey = "Ctrl+Alt+H"
dlg.accept(); print("accepted:", dlg.result() == 1)
s2 = st.Settings(os.path.join(out, "settings.json"))
print("saved:", {k: s2.get(k) for k in ("delay_seconds", "format", "quality", "filename_template",
                                        "history_keep_days", "history_max_items", "hotkey_history", "text_style")})
for i, name in enumerate(["Genel", "Kısayollar", "Kaydetme", "Geçmiş"]):
    dlg.findChild(type(dlg.layout().itemAt(0).widget())).setCurrentIndex(i); dlg.show(); app.processEvents()
    dlg.grab().save(os.path.join(out, f"dialog_{i}.png"))
dlg.close()

# ---- Windows ile başlat (test için ayrı bir kayıt adı)
st.set_autostart(True, name="MCBShot-test")
print("autostart cmd:", st.get_autostart("MCBShot-test"))
st.set_autostart(False, name="MCBShot-test")
print("autostart removed:", st.get_autostart("MCBShot-test") is None)

# ---- Geçmiş temizliği
store = HistoryStore(os.path.join(out, "hist"))
img = QImage(50, 50, QImage.Format.Format_RGB32); img.fill(QColor("red"))
ids = [store.add(img, [], img, 1.0) for _ in range(4)]
old_date = (datetime.now() - timedelta(days=40)).isoformat(timespec="seconds")
store.db.execute("UPDATE shots SET created_at = ? WHERE id = ?", (old_date, ids[0])); store.db.commit()
print("prune 30 days:", store.prune(30, 0), "left:", store.count())
print("prune max 2 (protect newest):", store.prune(0, 2, protect={ids[1]}), "left:", [e.id[-6:] for e in store.entries()])

# ---- Yazı arka planı: kutu / kontur
for style in ("none", "box", "glow"):
    base = QImage(300, 80, QImage.Format.Format_RGB32); base.fill(QColor("#888888"))
    t = TextItem(QColor("white"), 28, "Merhaba ğüş", style)
    t.setPos(10, 10)
    render_annotated(base, [t.state()]).save(os.path.join(out, f"text_{style}.png"))
print("text styles rendered")

# ---- Seçim ekranı: C ile renk kopyalama, ok tuşları
sess = overlay.CaptureSession(capture.capture_all(), s)
sess.start(); app.processEvents()
ov = sess.overlays[0]
ov._cursor_pos = QPointF(2500, 300)
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.NoModifier, "c"))
print("color copied:", QGuiApplication.clipboard().text(), "| flash:", ov._flash)
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ShiftModifier, "C"))
print("rgb copied:", QGuiApplication.clipboard().text())
ov.select_all(); before = ov.psel
ov.psel = before.adjusted(100, 100, -100, -100); ov._place_bars()
p0 = ov.psel.topLeft()
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier))
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier))
print("selection nudged:", p0, "->", ov.psel.topLeft())
from mcbshot.editor.items import RectItem
r = RectItem(QColor("red"), 3); r.set_geom_rect(r.rect.adjusted(0, 0, 50, 50)); r.setPos(500, 500)
ov._add_new(r); ov.select_only(r)
QApplication.sendEvent(ov, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier))
print("item nudged:", r.pos(), "undo text:", ov.undo_stack.text(ov.undo_stack.count() - 1))
print("new text style from settings:", ov.text_style)
sess.close()
print("OK")
