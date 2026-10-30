"""Kaydırmalı (tüm sayfa) ekran görüntüsü.

Seçilen alanın üzerine fare tekerleği gönderilerek içerik aşağı kaydırılır; her
adımda alan yeniden yakalanır. Yeni karenin üst kısmı, önceki karenin alt kısmıyla
satır satır eşleştirilerek ne kadar kaydığı bulunur ve sadece yeni görünen satırlar
eklenir. Sayfanın sabit üst/alt çubukları (menü, alt bilgi) bir kez alınır.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

import mss
import numpy as np
from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .i18n import tr

log = logging.getLogger("MCBShot")

MAX_HEIGHT = 30000        # fiziksel px; daha uzun sayfalar burada kesilir
MAX_STEPS = 120
MIN_OVERLAP = 24          # eşleştirme için gereken en az ortak satır
MATCH_THRESHOLD = 0.6     # ortak satırların en az bu oranı tutmalı
SETTLE_POLL_MS = 120      # kaydırma animasyonunun bitmesini beklerken yakalama aralığı
SETTLE_MAX_POLLS = 10

# ---- Windows: fare tekerleği ----
_user32 = ctypes.WinDLL("user32", use_last_error=True)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUT(ctypes.Structure):
    # MOUSEINPUT, birleşimdeki (union) en büyük üye olduğu için boyut doğru çıkar (64 bit: 40 bayt)
    _fields_ = [("type", wintypes.DWORD), ("mi", _MOUSEINPUT)]


_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
_user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
_MOUSEEVENTF_WHEEL = 0x0800
_WDA_EXCLUDEFROMCAPTURE = 0x11


def send_wheel(notches: int) -> None:
    """Fare tekerleğini aşağı doğru 'notches' kez çevir (imlecin altındaki pencereye gider)."""
    inp = _INPUT(type=0, mi=_MOUSEINPUT(0, 0, (-120 * notches) & 0xFFFFFFFF, _MOUSEEVENTF_WHEEL, 0, 0))
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


# ---- eşleştirme ----
def row_signatures(frame: np.ndarray) -> np.ndarray:
    """Her satır için bir özet (aynı satır = aynı değer)."""
    rgb = np.ascontiguousarray(frame[:, :, :3])
    return np.fromiter((hash(row.tobytes()) for row in rgb), dtype=np.int64, count=rgb.shape[0])


def informative_rows(frame: np.ndarray) -> np.ndarray:
    """Tek renk olmayan satırlar (boş satırlar her konumla eşleşeceği için sayılmaz)."""
    rgb = frame[:, :, :3]
    return ~np.all(rgb == rgb[:, :1, :], axis=(1, 2))


def find_offset(prev_sig: np.ndarray, cur_sig: np.ndarray, cur_info: np.ndarray,
                expected: int | None = None) -> int:
    """cur karesinin prev'e göre kaç satır aşağı kaydığını bulur. Bulunamazsa -1."""
    n = len(cur_sig)
    candidates = []
    for dy in range(1, n - MIN_OVERLAP + 1):
        info = cur_info[:n - dy]
        k = int(info.sum())
        if k < 8:
            continue
        m = int(np.count_nonzero((cur_sig[:n - dy] == prev_sig[dy:]) & info))
        candidates.append((m / k, dy))
    if not candidates:
        return -1
    best = max(score for score, _ in candidates)
    if best < MATCH_THRESHOLD:
        return -1
    good = [dy for score, dy in candidates if score >= best - 0.02]
    if expected:
        return min(good, key=lambda dy: abs(dy - expected))   # tekrar eden desenlerde beklenene en yakını
    return max(good)


class Stitcher:
    """Kareleri birleştirip tek uzun görüntü oluşturur."""

    def __init__(self, first: np.ndarray):
        self.first = first
        self.last = first
        self.h = first.shape[0]
        self.prev_sig = row_signatures(first)
        self.top: int | None = None      # sabit üst çubuğun bittiği satır
        self.bottom: int | None = None   # sabit alt çubuğun başladığı satır
        self.parts: list[np.ndarray] = []
        self.height = self.h

    @property
    def band(self) -> int:
        return (self.bottom - self.top) if self.top is not None else self.h

    def add(self, frame: np.ndarray, expected: int | None = None) -> int:
        """Yeni kare ekle. Dönüş: kayma (px), 0 = hiç kaymadı, -1 = eşleşme bulunamadı."""
        sig = row_signatures(frame)
        if np.array_equal(sig, self.prev_sig):
            return 0
        if self.top is None:
            # İlk kaymada: iki karede aynı yerde duran üst/alt satırlar = sabit çubuklar
            same = sig == self.prev_sig
            top = int(np.argmin(same)) if not same.all() else 0
            bottom = int(np.argmin(same[::-1])) if not same.all() else 0
            self.top = min(top, int(self.h * 0.4))
            self.bottom = self.h - min(bottom, int(self.h * 0.3))
            self.parts.append(self.first[:self.bottom])
        t, b = self.top, self.bottom
        dy = find_offset(self.prev_sig[t:b], sig[t:b], informative_rows(frame[t:b]), expected)
        if dy <= 0:
            return -1
        self.parts.append(frame[b - dy:b])
        self.height += dy
        self.prev_sig = sig
        self.last = frame
        return dy

    def result(self) -> np.ndarray:
        if self.top is None:
            return self.first
        return np.concatenate(self.parts + [self.last[self.bottom:]], axis=0)


def to_qimage(arr: np.ndarray) -> QImage:
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    return QImage(arr.tobytes(), w, h, w * 4, QImage.Format.Format_RGB32).copy()


# ---- kontrol penceresi ----
class ScrollControl(QWidget):
    stopRequested = Signal()
    cancelRequested = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            QWidget { background: #202124; color: #f0f0f0; font-size: 13px; }
            QPushButton { background: #34373c; border: 1px solid #555; border-radius: 4px; padding: 4px 10px; }
            QPushButton:hover { background: #2f8cff; }
        """)
        self.label = QLabel(tr("Kaydırmalı yakalama başlıyor…"))
        stop = QPushButton(tr("Bitir (Esc)"))
        cancel = QPushButton(tr("İptal"))
        stop.clicked.connect(self.stopRequested.emit)
        cancel.clicked.connect(self.cancelRequested.emit)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 6, 6)
        lay.addWidget(self.label)
        lay.addWidget(stop)
        lay.addWidget(cancel)

    def show_near(self, anchor: QRect) -> None:
        """anchor: seçimin mantıksal (Qt) global dikdörtgeni."""
        self.adjustSize()
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        x = min(max(anchor.left(), g.left() + 4), g.right() - self.width() - 4)
        y = anchor.top() - self.height() - 8
        if y < g.top():
            y = min(anchor.bottom() + 8, g.bottom() - self.height() - 4)
        self.move(x, y)
        self.show()
        # Kendisi ekran görüntüsüne hiç girmesin (Windows 10 2004 ve sonrası)
        _user32.SetWindowDisplayAffinity(int(self.winId()), _WDA_EXCLUDEFROMCAPTURE)


# ---- işi yürüten nesne ----
class ScrollCaptureJob(QObject):
    """Arayüzü dondurmadan zamanlayıcılarla adım adım çalışır."""

    finished = Signal(object, str)   # (QImage ya da None, açıklama)

    def __init__(self, rect: QRect, anchor: QRect, parent: QObject | None = None):
        """rect: yakalanacak alan (fiziksel, sanal masaüstü). anchor: aynı alanın mantıksal karşılığı."""
        super().__init__(parent)
        self.rect = QRect(rect)
        self.anchor = QRect(anchor)
        self._sct = mss.mss()
        self._stitcher: Stitcher | None = None
        self._notches = 0
        self._px_per_notch: float | None = None
        self._steps = 0
        self._no_move = 0
        self._polls = 0
        self._last_poll_sig = None
        self._done = False
        self._cursor_home = QCursor.pos()
        self.control = ScrollControl()
        self.control.stopRequested.connect(lambda: self.stop(cancel=False))
        self.control.cancelRequested.connect(lambda: self.stop(cancel=True))

    # ---- adımlar ----
    def start(self) -> None:
        self.control.show_near(self.anchor)
        r = self.rect
        # Tekerlek olayları imlecin altındaki pencereye gider: alanın sağ kenarına yakın bir nokta
        self._point = QPoint(r.right() - min(12, r.width() // 4), r.center().y())
        _user32.SetCursorPos(self._point.x(), self._point.y())
        QTimer.singleShot(250, self._first_frame)

    def _grab(self) -> np.ndarray:
        r = self.rect
        raw = self._sct.grab({"left": r.x(), "top": r.y(), "width": r.width(), "height": r.height()})
        return np.frombuffer(raw.bgra, dtype=np.uint8).reshape(raw.height, raw.width, 4).copy()

    def _first_frame(self) -> None:
        if self._done:
            return
        self._stitcher = Stitcher(self._grab())
        # Başlangıçta temkinli: alanın yaklaşık üçte biri kadar kaydır (çentik başına ~100 px varsayımı)
        self._notches = max(1, int(self.rect.height() * 0.35 / 100))
        self._scroll()

    def _scroll(self) -> None:
        if self._done:
            return
        self._steps += 1
        _user32.SetCursorPos(self._point.x(), self._point.y())
        send_wheel(self._notches)
        self._polls = 0
        self._last_poll_sig = None
        QTimer.singleShot(SETTLE_POLL_MS, self._wait_settle)

    def _wait_settle(self) -> None:
        """Yumuşak kaydırma animasyonu bitene kadar (iki ardışık kare aynı olana dek) bekle."""
        if self._done:
            return
        frame = self._grab()
        sig = row_signatures(frame)
        self._polls += 1
        if self._last_poll_sig is not None and np.array_equal(sig, self._last_poll_sig) \
                or self._polls >= SETTLE_MAX_POLLS:
            self._process(frame)
        else:
            self._last_poll_sig = sig
            QTimer.singleShot(SETTLE_POLL_MS, self._wait_settle)

    def _process(self, frame: np.ndarray) -> None:
        st = self._stitcher
        expected = int(self._px_per_notch * self._notches) if self._px_per_notch else None
        dy = st.add(frame, expected)
        if dy == 0:
            self._no_move += 1
            if self._no_move >= 2:      # iki kez kaymadıysa sayfanın sonuna gelindi
                self._finish("ok")
                return
        elif dy < 0:
            log.warning("Kaydırmalı yakalama: kareler eşleştirilemedi (adım %d)", self._steps)
            self._finish("nomatch")
            return
        else:
            self._no_move = 0
            self._px_per_notch = dy / self._notches
            # Sonraki adım: kayan bölgenin ~%60'ı (yeterli ortak alan kalsın)
            self._notches = max(1, int(st.band * 0.6 / max(1.0, self._px_per_notch)))
        self.control.label.setText(tr("Kaydırılıyor…  {height} px", height=st.height))
        if st.height >= MAX_HEIGHT or self._steps >= MAX_STEPS:
            self._finish("limit")
            return
        self._scroll()

    # ---- bitiş ----
    def stop(self, cancel: bool = False) -> None:
        if cancel:
            self._finish("cancel")
        else:
            self._finish("ok")

    def _finish(self, reason: str) -> None:
        if self._done:
            return
        self._done = True
        self.control.close()
        self.control.deleteLater()
        QCursor.setPos(self._cursor_home)
        try:
            self._sct.close()
        except Exception:
            pass
        image = None
        if reason != "cancel" and self._stitcher is not None:
            arr = self._stitcher.result()
            if arr.shape[0] > MAX_HEIGHT:
                arr = arr[:MAX_HEIGHT]
            image = to_qimage(arr)
        self.finished.emit(image, reason)
