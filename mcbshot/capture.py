"""Ekran yakalama (mss ile, her monitör kendi fiziksel çözünürlüğünde).

High-DPI notu: Qt pencereleri "mantıksal" piksellerle çalışır (ör. %150 ölçekte
2560 px genişliğindeki ekran 1707 mantıksal px'tir). mss ise gerçek (fiziksel)
pikselleri yakalar. Her ekranın fiziksel dikdörtgenini Windows API'sinden alıp
Qt'nin QScreen nesnesiyle eşleştiriyoruz; böylece farklı ölçekli monitörlerde
koordinatlar kaymaz.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import mss
from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QRegion, QScreen

_user32 = ctypes.WinDLL("user32", use_last_error=True)


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


_MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM
)
_user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), _MonitorEnumProc, wintypes.LPARAM]
_user32.EnumDisplayMonitors.restype = wintypes.BOOL
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFOEXW)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL


@dataclass
class ScreenShot:
    """Bir seçim penceresinin kapsadığı alanın görüntüsü.

    Tüm monitörlerin ölçeği aynıysa tek bir ScreenShot bütün sanal masaüstünü kapsar
    (seçim monitörler arasında yayılabilir). Ölçekler farklıysa her monitör için ayrı
    bir ScreenShot olur.
    """

    screens: list[QScreen]
    image: QImage            # fiziksel piksel çözünürlüğünde görüntü
    physical: QRect          # sanal masaüstündeki fiziksel konum/boyut
    dpr: float               # fiziksel / mantıksal piksel oranı (ör. %150 ölçek -> 1.5)
    screen_rects: list[QRect]  # her monitörün görüntü içindeki fiziksel dikdörtgeni

    @property
    def screen(self) -> QScreen:
        return self.screens[0]

    @property
    def spans(self) -> bool:
        return len(self.screens) > 1


def _physical_monitors() -> list[tuple[str, QRect]]:
    monitors: list[tuple[str, QRect]] = []

    def callback(hmon, hdc, lprect, lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if _user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            monitors.append((info.szDevice, QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    _user32.EnumDisplayMonitors(None, None, _MonitorEnumProc(callback), 0)
    return monitors


def _physical_rect_for(screen: QScreen, monitors: list[tuple[str, QRect]], index: int) -> QRect:
    # 1) Aygıt adıyla eşleştir (\\.\DISPLAY1 gibi)
    for device, rect in monitors:
        if device == screen.name():
            return rect
    # 2) Qt, ekranın sol üst köşesini fiziksel koordinatta tutar
    top_left = screen.geometry().topLeft()
    for _, rect in monitors:
        if rect.topLeft() == top_left:
            return rect
    # 3) Sıra ile eşleştir
    if index < len(monitors):
        return monitors[index][1]
    # 4) Son çare: mantıksal boyut x ölçek
    g = screen.geometry()
    d = screen.devicePixelRatio()
    return QRect(g.x(), g.y(), round(g.width() * d), round(g.height() * d))


def _grab(sct, rect: QRect) -> QImage:
    raw = sct.grab({"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()})
    return QImage(raw.bgra, raw.width, raw.height, raw.width * 4, QImage.Format.Format_RGB32).copy()


def capture_all(allow_span: bool = True) -> list[ScreenShot]:
    """Ekranları yakalar.

    Bütün monitörlerin ölçeği aynıysa (ve allow_span ise) tek bir ScreenShot döner:
    sanal masaüstünün tamamı, seçim monitörler arasında yayılabilir. Aksi halde
    her monitör için ayrı bir ScreenShot döner.
    """
    monitors = _physical_monitors()
    screens = QGuiApplication.screens()
    rects = [_physical_rect_for(s, monitors, i) for i, s in enumerate(screens)]
    dprs = [r.width() / s.geometry().width() if s.geometry().width() else 1.0 for s, r in zip(screens, rects)]

    with mss.mss() as sct:
        if allow_span and len(screens) > 1 and max(dprs) - min(dprs) < 0.01:
            union = QRect(rects[0])
            for r in rects[1:]:
                union = union.united(r)
            image = _grab(sct, union)
            # Hiçbir monitörün göstermediği köşeler (farklı yükseklikteki monitörler) siyah kalsın
            local = [r.translated(-union.topLeft()) for r in rects]
            hidden = QRegion(image.rect())
            for r in local:
                hidden -= QRegion(r)
            if not hidden.isEmpty():
                p = QPainter(image)
                for r in hidden:
                    p.fillRect(r, QColor(0, 0, 0))
                p.end()
            return [ScreenShot(list(screens), image, union, dprs[0], local)]
        return [ScreenShot([s], _grab(sct, r), r, d, [QRect(0, 0, r.width(), r.height())])
                for s, r, d in zip(screens, rects, dprs)]
