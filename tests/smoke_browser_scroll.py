"""Gerçek tarayıcıda (Edge, geçici profil) kaydırmalı yakalama testi."""
import ctypes, os, subprocess, sys, tempfile, time
from ctypes import wintypes
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
out = os.path.join(os.environ["TEMP"], "mcbs-browser"); os.makedirs(out, exist_ok=True)
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication
QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
app = QApplication(sys.argv)
from mcbshot import scroll

TITLE = "MCBShotKaydirmaTesti"
rows = "\n".join(
    f'<p class="r{i % 5}">{i}. paragraf — Türkçe karakterler: ğüşıöç ĞÜŞİÖÇ. '
    f'Lorem ipsum dolor sit amet, consectetur adipiscing elit {i * 7919 % 1000}.</p>' +
    (f'<div class="box" style="background:hsl({i * 37 % 360},70%,60%)">Kutu {i}</div>' if i % 6 == 0 else "")
    for i in range(1, 181))
html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{TITLE}</title><style>
body {{ margin:0; font-family:Segoe UI, sans-serif; font-size:17px; }}
header {{ position:sticky; top:0; background:#1d3557; color:white; padding:14px 20px; font-size:22px; }}
main {{ padding: 10px 24px; }}
.box {{ height:90px; margin:12px 0; color:white; font-weight:bold; padding:10px; }}
.r0 {{ color:#222 }} .r1 {{ color:#444 }} .r2 {{ color:#1d6f42 }} .r3 {{ color:#7a1f1f }} .r4 {{ color:#333; font-style:italic }}
</style></head><body><header>Sabit başlık (position: sticky)</header><main>{rows}<p><b>SAYFANIN SONU</b></p></main></body></html>"""
page = os.path.join(out, "test.html")
with open(page, "w", encoding="utf-8") as f:
    f.write(html)

edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(edge):
    edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
profile = tempfile.mkdtemp(prefix="mcbs-edge-")
proc = subprocess.Popen([edge, f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                         "--inprivate", "--new-window", "--window-position=200,100", "--window-size=1100,900", page])

user32 = ctypes.windll.user32
def find_window():
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(512); user32.GetWindowTextW(hwnd, buf, 512)
        if TITLE in buf.value and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(cb, 0)
    return found[0] if found else None

hwnd = None
t0 = time.time()
while hwnd is None and time.time() - t0 < 30:
    time.sleep(0.5); hwnd = find_window()
print("edge window:", bool(hwnd))
if hwnd:
    time.sleep(2.5)   # sayfa yüklensin
    user32.SetForegroundWindow(hwnd)
    r = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
    # Tarayıcı araç çubuklarını atla: pencerenin üstünden ~140 px aşağısı, kenarlardan 20 px içeri
    sel = QRect(r.left + 20, r.top + 140, (r.right - r.left) - 60, (r.bottom - r.top) - 170)
    print("window:", (r.left, r.top, r.right - r.left, r.bottom - r.top), "selection:", sel)
    result = {}
    job = scroll.ScrollCaptureJob(sel, sel)
    job.finished.connect(lambda img, reason: result.update(img=img, reason=reason))
    t0 = time.time(); job.start()
    while "reason" not in result and time.time() - t0 < 180:
        app.processEvents(); time.sleep(0.01)
    img = result.get("img")
    print("reason:", result.get("reason"), "time: %.1fs" % (time.time() - t0), "steps:", job._steps,
          "static top/bottom:", job._stitcher.top, job._stitcher.bottom, "band:", job._stitcher.band)
    print("result:", img.size() if img else None)
    if img:
        img.save(os.path.join(out, "edge_stitched.png"))
        from mcbshot import ocr
        text = ocr.recognize(img).text
        nums = [int(w.split(".")[0]) for w in text.split() if w.endswith(".") and w[:-1].isdigit()]
        print("OCR: paragraf numaraları bulundu:", len(set(nums)), "en büyük:", max(nums) if nums else None,
              "| 'SAYFANIN SONU' var mı:", "SAYFANIN SONU" in text.upper())
    user32.PostMessageW(hwnd, 0x0010, 0, 0)   # WM_CLOSE
time.sleep(1.5)
try:
    proc.terminate()
except Exception:
    pass
print("OK")
