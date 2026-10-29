"""Kaydırmalı yakalama testi: kendi kaydırılabilir penceremizi gerçek fare tekerleğiyle kaydırıp birleştiririz.

Kullanım: python smoke_scroll.py [içerik_yüksekliği] [başlık_yüksekliği] [alt_çubuk_yüksekliği]
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-scroll"); os.makedirs(out, exist_ok=True)
import numpy as np
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor, QFont, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QVBoxLayout, QWidget
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot import scroll

W = 860
H = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
HEADER = int(sys.argv[2]) if len(sys.argv) > 2 else 60
FOOTER = int(sys.argv[3]) if len(sys.argv) > 3 else 0
content = QImage(W, H, QImage.Format.Format_RGB32); content.fill(QColor("white"))
p = QPainter(content); f = QFont("Segoe UI"); f.setPixelSize(18); p.setFont(f)
y = 0; n = 0
while y < H:
    n += 1
    if n % 25 == 0:          # boş bölümler (tek renk satırlar)
        y += 220; continue
    if 60 <= n < 70:         # tekrar eden desen
        p.fillRect(20, y + 8, 300, 20, QColor("#4a90d9")); y += 36; continue
    p.setPen(QColor("black")); p.drawText(20, y + 26, f"Satır {n}: MCBShot kaydırmalı yakalama testi ğüşiöç")
    p.fillRect(560 + (n * 37) % 250, y + 8, 30, 22, QColor.fromHsv((n * 23) % 360, 180, 220))
    y += 40
p.end()

win = QWidget(None, Qt.WindowType.WindowStaysOnTopHint)
win.setWindowTitle("Kaydırma testi")
lay = QVBoxLayout(win); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0)
if HEADER:
    header = QLabel("  SABİT BAŞLIK (kaydırılmaz)"); header.setFixedHeight(HEADER)
    header.setStyleSheet("background:#203040;color:white;font-size:20px")
    lay.addWidget(header)
area = QScrollArea(); area.setFrameShape(QScrollArea.Shape.NoFrame)
lbl = QLabel(); lbl.setPixmap(QPixmap.fromImage(content)); area.setWidget(lbl)
area.verticalScrollBar().setSingleStep(20)
lay.addWidget(area)
if FOOTER:
    footer = QLabel("  sabit alt çubuk  •  © MCBShot"); footer.setFixedHeight(FOOTER)
    footer.setStyleSheet("background:#e0e0e0;color:#333;font-size:14px;border-top:1px solid #999")
    lay.addWidget(footer)
VIEW = 700
win.setGeometry(300, 150, W + area.verticalScrollBar().sizeHint().width(), HEADER + VIEW + FOOTER)
win.show(); win.raise_(); win.activateWindow()
for _ in range(20): app.processEvents(); time.sleep(0.02)

# Seçim: başlık + kaydırma alanının görünen kısmı + alt çubuk (kaydırma çubuğu hariç)
tl = win.mapToGlobal(QPoint(0, 0))
sel = QRect(tl.x(), tl.y(), W, win.height())
print("selection:", sel, "content:", W, "x", H, "header:", HEADER, "footer:", FOOTER)
result = {}
job = scroll.ScrollCaptureJob(sel, sel)
job.finished.connect(lambda img, reason: result.update(img=img, reason=reason))
t0 = time.time()
job.start()
while "reason" not in result and time.time() - t0 < 120:
    app.processEvents(); time.sleep(0.01)
img = result.get("img")
print("reason:", result.get("reason"), "time: %.1fs" % (time.time() - t0), "steps:", job._steps,
      "static top/bottom:", job._stitcher.top, job._stitcher.bottom)
print("result size:", img.size() if img else None, "expected height:", HEADER + H + FOOTER)
img.save(os.path.join(out, "stitched.png"))

def arr(qimg):
    q = qimg.convertToFormat(QImage.Format.Format_RGB32)
    return np.frombuffer(q.constBits(), np.uint8).reshape(q.height(), q.bytesPerLine() // 4, 4)[:, :q.width(), :3]
res = arr(img)
ref = arr(content)
body = res[HEADER:res.shape[0] - FOOTER]
h = min(body.shape[0], ref.shape[0])
M = 10   # Windows 11'in yuvarlak pencere köşeleri kenar piksellerini değiştirir: kenarları sayma
rows = np.nonzero(np.any(body[:h, M:W - M] != ref[:h, M:W - M], axis=(1, 2)))[0]
runs = np.split(rows, np.nonzero(np.diff(rows) > 1)[0] + 1) if len(rows) else []
print("diff runs (edges excluded):", [(int(r[0]), int(r[-1])) for r in runs][:20])
print("compared rows:", h, "different rows:", len(rows), "height match:", body.shape[0] == ref.shape[0])
win.close()
print("OK")
