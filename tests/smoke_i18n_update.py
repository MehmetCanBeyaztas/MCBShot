"""Çeviri ve güncelleme denetimi.

- Kaynaktaki her tr("...") / N_("...") metninin İngilizce karşılığı var mı, {yer tutucular} aynı mı?
- İngilizce arayüzde pencerelerde Türkçe harf kalmış mı?
- Sürüm karşılaştırma, GitHub yanıtından dosya seçme, iki dilli sürüm notlarını ayırma.
- (İnternet varsa) GitHub'daki son sürüm okunabiliyor mu?
"""
import ast
import os
import re
import string
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QTabWidget

qapp = QApplication(sys.argv)

from mcbshot import i18n, updater
from mcbshot.i18n import EN, tr

# ---- 1) kaynak metinlerin hepsi sözlükte mi ----
def literals():
    for folder, _, files in os.walk(os.path.join(ROOT, "mcbshot")):
        for name in files:
            if not name.endswith(".py") or name == "i18n.py":
                continue
            path = os.path.join(folder, name)
            tree = ast.parse(open(path, encoding="utf-8-sig").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("tr", "N_") and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        yield name, arg.value

def fields(text):
    return sorted(f for _, f, _, _ in string.Formatter().parse(text) if f)

missing, mismatched, count = [], [], 0
for fname, text in literals():
    count += 1
    if text not in EN:
        missing.append((fname, text))
    elif fields(text) != fields(EN[text]) and "{tarih}" not in text:
        mismatched.append((fname, text))
print("translatable strings:", count)
assert not missing, "İngilizcesi olmayan metinler:\n" + "\n".join(f"  {f}: {t!r}" for f, t in missing)
assert not mismatched, "Yer tutucuları farklı:\n" + "\n".join(f"  {f}: {t!r}" for f, t in mismatched)
assert count > 150, count

i18n.set_language("en")
assert tr("Kaydedildi: {name}", name="a.png") == "Saved: a.png"
assert tr("%{value}", value=90) == "90%"
i18n.set_language("tr")
assert tr("Kaydedildi: {name}", name="a.png") == "Kaydedildi: a.png"
assert tr("%{value}", value=90) == "%90"
print("system language:", i18n.system_language())

# ---- 2) İngilizce pencerelerde Türkçe kalmamış olmalı ----
from mcbshot.export import render_filename
from datetime import datetime
assert render_filename("{date}_{time}", datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02_03-04-05"
assert render_filename("{tarih}_{saat}", datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02_03-04-05"

i18n.set_language("en")
tmp = tempfile.mkdtemp(prefix="mcbs-i18n-")
import mcbshot.history as hist
hist.history_dir = lambda: __import__("pathlib").Path(tmp) / "history"
from mcbshot.gallery import GalleryWindow
from mcbshot.history import HistoryStore
from mcbshot.settings import Settings
from mcbshot.settings_window import SettingsDialog

TURKISH = re.compile("[çğıöşüÇĞİÖŞÜ]")

def texts(widget):
    out = [widget.windowTitle()]
    for w in widget.findChildren(QLabel):
        out.append(w.text())
    for w in widget.findChildren(QAbstractButton):
        out += [w.text(), w.toolTip()]
    for w in widget.findChildren(QLineEdit):
        out.append(w.placeholderText())
    for w in widget.findChildren(QComboBox):
        out += [w.itemText(i) for i in range(w.count())]
    for w in widget.findChildren(QTabWidget):
        out += [w.tabText(i) for i in range(w.count())]
    return [t for t in out if t]

settings = Settings(os.path.join(tmp, "settings.json"))
store = HistoryStore()
for win in (SettingsDialog(settings, history_count=3), GalleryWindow(store, settings)):
    found = [t for t in texts(win) if TURKISH.search(t) and t != "Türkçe"]
    assert not found, f"{type(win).__name__}: {found}"
    print(type(win).__name__, "english ok:", win.windowTitle())
    win.deleteLater()
store.close()
i18n.set_language("tr")

# ---- 3) güncelleme mantığı ----
assert updater.parse_version("v1.2.10") == (1, 2, 10)
assert updater.parse_version("1.1.0-beta") == (1, 1, 0)
assert updater.is_newer("1.1.0", "1.0.0") and updater.is_newer("v1.0.10", "1.0.9")
assert not updater.is_newer("1.0.0", "1.0.0") and not updater.is_newer("0.9", "1.0.0")

prefix = updater.DOWNLOAD_PREFIX + "v9.9.9/"
data = {
    "tag_name": "v9.9.9", "html_url": "https://github.com/x", "body": "notes",
    "assets": [
        {"name": "MCBShot-Setup-9.9.9.exe", "browser_download_url": prefix + "MCBShot-Setup-9.9.9.exe", "size": 5},
        {"name": "MCBShot.exe", "browser_download_url": prefix + "MCBShot.exe", "size": 7,
         "digest": "sha256:ABC"},
        {"name": "MCBShot.exe", "browser_download_url": "https://evil.example/MCBShot.exe", "size": 1},
    ],
}
rel = updater.release_from_json(data)   # geliştirme kopyası = taşınabilir sayılır
assert rel.version == "9.9.9" and rel.asset_name == "MCBShot.exe" and rel.size == 7 and rel.sha256 == "abc", rel
updater.is_installed = lambda: True
rel = updater.release_from_json(data)
assert rel.asset_name == "MCBShot-Setup-9.9.9.exe" and rel.sha256 is None, rel
data["assets"] = data["assets"][2:]
assert updater.release_from_json(data).asset_url == ""   # başka adresteki dosya kabul edilmez
try:
    updater.release_from_json({"tag_name": "latest"})
    raise AssertionError("geçersiz etiket kabul edildi")
except ValueError:
    pass

notes = ('**Türkçe** · [English](#english)\n\n## Sürüm\n- yeni\n\n---\n\n<a id="english"></a>\n\n'
         '## Release\n- new\n')
assert updater.notes_for_language(notes, "tr") == "## Sürüm\n- yeni", repr(updater.notes_for_language(notes, "tr"))
assert updater.notes_for_language(notes, "en") == "## Release\n- new"
assert updater.notes_for_language("plain", "en") == "plain"

# indirilen dosyanın doğrulanması
p = os.path.join(tmp, "f.bin")
open(p, "wb").write(b"hello")
import hashlib
from pathlib import Path
good = updater.Release("1", "", "", "f.bin", "", 5, hashlib.sha256(b"hello").hexdigest())
assert updater._verify(Path(p), good)
assert not updater._verify(Path(p), updater.Release("1", "", "", "f.bin", "", 6, None))
assert not updater._verify(Path(p), updater.Release("1", "", "", "f.bin", "", 5, "00"))

try:
    latest = updater.fetch_latest()
    print("github latest:", latest.version, latest.asset_name or "(no asset)")
except Exception as ex:   # internet yoksa test geçsin
    print("github check skipped:", ex)

import shutil
shutil.rmtree(tmp, ignore_errors=True)
print("OK")
