"""Kaydırmalı yakalamada eşleştirme: seçime sabit şeyler (panel çizgisi, açılır kutu) girse de kareler birleşmeli."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
from mcbshot.scroll import STILL_RATIO, Stitcher, find_offset, pixel_values

W, H, VIEW = 1400, 4000, 900
rng = np.random.default_rng(7)
page = np.full((H, W, 4), 255, dtype=np.uint8)
for y in range(40, H - 40, 44):          # "yazı" satırları: rastgele uzunlukta, düzensiz bloklar
    for x in range(60, int(rng.integers(300, W - 60)), 13):
        page[y:y + 18, x:x + int(rng.integers(3, 11)), :3] = rng.integers(0, 90, 3)
for y in range(600, 1500, 300):          # görsel: tarayıcı her karede ±1 oynatabilir
    page[y:y + 200, 200:1200, :3] = rng.integers(120, 230, (200, 1000, 3))


def view(pos, noise=False):
    f = page[pos:pos + VIEW].copy()
    if noise:
        img = f[:, 200:1200, :3]
        f[:, 200:1200, :3] = np.where(img < 250, img ^ rng.integers(0, 2, img.shape, dtype=np.uint8), img)
    f[100:800, 7:9, :3] = (150, 150, 150)                  # sayfa kayarken yerinde duran panel çizgisi
    f[VIEW - 130:VIEW - 20, W - 320:W - 20, :3] = (250, 245, 235)   # sabit açılır kutu
    f[VIEW - 100:VIEW - 90, W - 300:W - 60, :3] = (20, 20, 20)
    return f


# Eski yöntem (satır bütün olarak) bu karelerde eşleşme bulamıyordu
assert find_offset(pixel_values(view(0)), pixel_values(view(450)), None) == 450
assert find_offset(pixel_values(view(0)), pixel_values(view(450)), 450) == 450

# İçerik karenin altında yoğun: ortak alanda az piksel kalsa da doğru kayma bulunmalı (SAP sayfası, 544 px seçim)
dense = np.full((1200, W, 4), 255, dtype=np.uint8)
for y in range(0, 300, 44):
    dense[y:y + 6, 100:160, :3] = rng.integers(0, 90, 3)
dense[320:1200, 100:1300, :3] = rng.integers(0, 200, (880, 1200, 3))
assert find_offset(pixel_values(dense[:544]), pixel_values(dense[300:844])) == 300

# Baştan sona birleştirme: sonuç tam sayfa boyunda ve içerik yerinde olmalı
st = Stitcher(view(0))
pos = 0
while pos + VIEW < H:
    step = min(450, H - VIEW - pos)
    pos += step
    dy = st.add(view(pos, noise=True), 450 if pos > 450 else None)
    assert dy == step, (pos, dy, step)
result = st.result()
assert result.shape[0] == H, result.shape
diff = np.abs(result[:, 400:1000, :3].astype(np.int16) - page[:, 400:1000, :3])
same = np.mean((diff <= 1).all(axis=2))
assert same > 0.97, same
print("stitched:", result.shape, "same pixels: %.4f" % same)

# Sayfa sonu: kayma yok ama küçük bir şey (yanıp sönen imleç) değişiyor -> yine "kaymadı" sayılmalı
last = view(H - VIEW)
blink = last.copy()
blink[200:230, 600:602, :3] = 0
assert (pixel_values(blink) != pixel_values(last)).mean() < STILL_RATIO
assert st.add(blink) == 0

# Sayfa sonu seçimin altında kalabilir: gerçek alt çubuk yoksa kalan kısım istenmeli
assert st.wants_tail()
blank_end = Stitcher(page[0:300].copy())
blank_end.top, blank_end.bottom, blank_end.last = 0, 299, page[300:600].copy()
blank_end.first[299:, :, :3] = 255
blank_end.last[299:, :, :3] = 255
assert blank_end.wants_tail()               # tek boş satır alt çubuk değildir
footer = page[0:300].copy()
footer[260:, :, :3] = 200
footer[270:290, 100:400, :3] = 30
real_footer = Stitcher(footer)
real_footer.top, real_footer.bottom = 0, 260
moved = page[300:600].copy()
moved[260:] = footer[260:]
real_footer.last = moved
assert not real_footer.wants_tail()         # gerçek alt çubuk varsa sayfa sonu zaten seçimdedir

# İlgisiz iki kare eşleşmemeli
other = rng.integers(0, 255, (VIEW, W, 4), dtype=np.uint8)
assert find_offset(pixel_values(view(0)), pixel_values(other)) == -1
print("OK")
