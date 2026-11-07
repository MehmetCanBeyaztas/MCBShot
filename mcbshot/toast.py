"""Windows bildirimleri (toast): ad ve simge kaydı, ekran görüntüsü önizlemesi, tıklayınca açılan bağlantı.

Program kısayolsuz çalıştığında da (taşınabilir sürüm) bildirimlerde "MCBShot" adı ve simgesi
görünsün diye uygulama kimliği HKCU\\Software\\Classes\\AppUserModelId altına kaydedilir.
Modern bildirim gösterilemezse çağıran taraf eski tepsi balonuna düşer.
"""
from __future__ import annotations

import logging
import os
import time
import winreg
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from . import APP_NAME

log = logging.getLogger(APP_NAME)

AUMID = APP_NAME
PREVIEW_WIDTH = 728            # bildirim ~364 px genişlik; 2 kat keskin görünsün
PREVIEW_MAX_RATIO = 0.75       # uzun görüntülerde yalnızca üst kısım (yükseklik ≤ genişlik × 0.75)
_AUMID_KEY = rf"Software\Classes\AppUserModelId\{AUMID}"


def _folder() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME / "notifications"
    path.mkdir(parents=True, exist_ok=True)
    return path


def register(icon_image: QImage) -> None:
    """Bildirimlerde görünen adı ve simgeyi Windows'a kaydeder."""
    icon = _folder() / "icon.png"
    icon_image.save(str(icon), "PNG")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _AUMID_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))


def preview_file(image: QImage) -> Path:
    """Bildirimde gösterilecek küçük önizleme (uzun görüntülerin üst kısmı)."""
    img = image
    if img.width() > PREVIEW_WIDTH:
        img = img.scaledToWidth(PREVIEW_WIDTH, Qt.TransformationMode.SmoothTransformation)
    max_h = int(img.width() * PREVIEW_MAX_RATIO)
    if img.height() > max_h:
        img = img.copy(0, 0, img.width(), max_h)
    folder = _folder()
    for old in folder.glob("preview-*.png"):   # Windows görüntüyü adına göre önbelleğe alır: her seferinde yeni ad
        try:
            old.unlink()
        except OSError:
            pass
    path = folder / f"preview-{time.time_ns()}.png"
    if not img.save(str(path), "PNG"):
        raise OSError("preview")
    return path


class Notifier(QObject):
    """Bildirim gösterir. Tıklama Windows tarafından açılan bir bağlantıdır (klasör ya da web sayfası):
    kısayolu olmayan programlara Windows tıklama olayı iletmediği için."""

    _failed = Signal(object)    # arka plan iş parçacığından arayüze

    def __init__(self, fallback, parent: QObject | None = None):
        """fallback(text, link): modern bildirim gösterilemezse çağrılır (tepsi balonu)."""
        super().__init__(parent)
        self.fallback = fallback
        self._live: dict[int, tuple] = {}    # "gösterilemedi" olayı gelebilsin diye bildirimler bir süre yaşar
        self._failed.connect(self._on_failed, Qt.ConnectionType.QueuedConnection)
        self._notifier = None
        try:
            from winrt.windows.ui.notifications import ToastNotificationManager
            self._notifier = ToastNotificationManager.create_toast_notifier_with_id(AUMID)
        except Exception:
            log.exception("Windows bildirimleri kullanılamıyor; tepsi balonu kullanılacak")

    def show(self, text: str, link: str | None = None, image: QImage | None = None) -> bool:
        """link: tıklanınca açılacak web adresi ya da klasör yolu."""
        if self._notifier is None:
            return False
        try:
            from winrt.windows.data.xml.dom import XmlDocument
            from winrt.windows.ui.notifications import ToastNotification

            title, _, body = text.partition("\n")
            parts = [f"<text>{escape(title)}</text>"]
            if body.strip():
                parts.append(f"<text>{escape(body.strip())}</text>")
            if image is not None and not image.isNull():
                parts.append(f"<image src={quoteattr(preview_file(image).as_uri())}/>")
            launch = ""
            if link:
                uri = link if "://" in link else Path(link).as_uri()
                launch = f' activationType="protocol" launch={quoteattr(uri)}'
            doc = XmlDocument()
            doc.load_xml(f'<toast{launch}><visual><binding template="ToastGeneric">' + "".join(parts) +
                         "</binding></visual></toast>")
            toast = ToastNotification(doc)
            key = id(toast)
            toast.add_failed(lambda *_: self._failed.emit(key))
            self._live[key] = (toast, text, link)
            while len(self._live) > 20:
                self._live.pop(next(iter(self._live)))
            self._notifier.show(toast)
            return True
        except Exception:
            log.exception("Bildirim gösterilemedi")
            return False

    def _on_failed(self, key) -> None:
        entry = self._live.pop(key, None)
        if entry:
            log.warning("Windows bildirimi reddetti; tepsi balonu kullanılıyor")
            self.fallback(entry[1], entry[2])

    def clear(self) -> None:
        """Program kapanırken Bildirim Merkezi'ndeki bildirimleri kaldır."""
        try:
            from winrt.windows.ui.notifications import ToastNotificationManager
            ToastNotificationManager.history.clear_with_id(AUMID)
        except Exception:
            pass
        self._live.clear()
