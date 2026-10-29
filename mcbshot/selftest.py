"""Paketlenmiş .exe'nin çalıştığını doğrulamak için kendi kendini sınama.

Kullanım:  MCBShot.exe --selftest   (sonuç: %TEMP%\\mcbshot_selftest.txt)
"""
from __future__ import annotations

import os
import tempfile
import traceback


def run() -> int:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication([])
    lines: list[str] = []
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            lines.append(f"[OK]   {name}: {fn()}")
        except Exception:
            ok = False
            lines.append(f"[HATA] {name}:\n{traceback.format_exc()}")

    from . import capture, export, ocr
    from .history import HistoryStore

    check("ekran yakalama", lambda: [(s.physical.getRect(), s.spans) for s in capture.capture_all()])

    img = QImage(900, 160, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    f = QFont("Segoe UI")
    f.setPixelSize(40)
    p.setFont(f)
    p.setPen(QColor("black"))
    p.drawText(20, 90, "Merhaba dünya ğüşıöç 2026")
    p.end()
    check("OCR", lambda: repr(ocr.recognize(img).text))

    def history():
        with tempfile.TemporaryDirectory(prefix="mcbs-selftest-") as tmp:
            store = HistoryStore(tmp)
            entry_id = store.add(img, [], img, 1.0)
            n = store.count()
            store.close()
        return f"{n} kayıt ({entry_id})"
    check("geçmiş veritabanı", history)

    def formats():
        with tempfile.TemporaryDirectory(prefix="mcbs-selftest-") as tmp:
            for fmt in ("png", "jpg", "webp"):
                export.save_image(img, os.path.join(tmp, f"t.{fmt}"), fmt, 90)
        return "png/jpg/webp kaydedildi"
    check("dosya formatları", formats)

    import numpy
    check("numpy", lambda: numpy.__version__)

    report = os.path.join(tempfile.gettempdir(), "mcbshot_selftest.txt")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n" + ("SONUÇ: BAŞARILI" if ok else "SONUÇ: HATA VAR") + "\n")
    app.quit()
    return 0 if ok else 1
