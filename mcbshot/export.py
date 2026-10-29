"""Panoya kopyalama ve dosyaya kaydetme yardımcıları."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QImage, QImageWriter

# ayar adı -> (Qt format adı, uzantı)
FORMATS = {
    "png": ("PNG", ".png"),
    "jpg": ("JPG", ".jpg"),
    "webp": ("WEBP", ".webp"),
}
FILE_FILTERS = {
    "png": "PNG resmi (*.png)",
    "jpg": "JPG resmi (*.jpg *.jpeg)",
    "webp": "WebP resmi (*.webp)",
}
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def render_filename(template: str, now: datetime | None = None) -> str:
    """'{tarih}_{saat}' gibi bir şablondan dosya adı (uzantısız) üretir."""
    now = now or datetime.now()
    values = {
        "tarih": now.strftime("%Y-%m-%d"),
        "saat": now.strftime("%H-%M-%S"),
        "yil": now.strftime("%Y"),
        "ay": now.strftime("%m"),
        "gun": now.strftime("%d"),
    }
    try:
        name = template.format(**values)
    except (KeyError, IndexError, ValueError):
        name = "MCBShot_{tarih}_{saat}".format(**values)
    name = _INVALID_CHARS.sub("_", name).strip(" .")
    return name or "MCBShot"


def unique_path(folder: str | Path, stem: str, ext: str) -> Path:
    folder = Path(folder)
    path = folder / f"{stem}{ext}"
    i = 2
    while path.exists():
        path = folder / f"{stem}_{i}{ext}"
        i += 1
    return path


def format_from_path(path: str | Path, default: str = "png") -> str:
    ext = Path(path).suffix.lower()
    if ext == ".png":
        return "png"
    if ext in (".jpg", ".jpeg"):
        return "jpg"
    if ext == ".webp":
        return "webp"
    return default


def is_format_supported(fmt: str) -> bool:
    qt_name = FORMATS[fmt][0].lower()
    return any(f.data().decode().lower() == qt_name for f in QImageWriter.supportedImageFormats())


def save_image(image: QImage, path: str | Path, fmt: str, quality: int = 90) -> None:
    """Görüntüyü kaydeder; başarısız olursa OSError fırlatır."""
    if fmt not in FORMATS:
        fmt = "png"
    if not is_format_supported(fmt):
        raise OSError(f"{FORMATS[fmt][0]} formatı bu sistemde desteklenmiyor.")
    img = image
    if fmt == "jpg":
        img = image.convertToFormat(QImage.Format.Format_RGB888)  # JPG saydamlık desteklemez
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    q = -1 if fmt == "png" else max(1, min(100, int(quality)))
    if not img.save(str(path), FORMATS[fmt][0], q):
        raise OSError(f"Dosya kaydedilemedi: {path}")


def copy_image(image: QImage) -> None:
    QGuiApplication.clipboard().setImage(image)


def copy_text(text: str) -> None:
    QGuiApplication.clipboard().setText(text)


def choose_save_target(parent, settings, quick: bool, suggested: str | None = None) -> tuple[Path, str] | None:
    """Kaydedilecek dosya yolunu ve formatı belirler.

    quick=True: sormadan varsayılan klasöre şablonlu adla. Aksi halde kaydetme penceresi
    açılır; vazgeçilirse None döner.
    """
    from PySide6.QtWidgets import QFileDialog

    fmt = settings.get("format") if settings.get("format") in FORMATS else "png"
    if suggested:
        path = Path(suggested)
        fmt = format_from_path(path, fmt)
    else:
        folder = settings.get("save_dir") if quick else (settings.get("last_save_dir") or settings.get("save_dir"))
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = str(Path.home())
        path = unique_path(folder, render_filename(settings.get("filename_template")), FORMATS[fmt][1])
    if quick:
        return path, fmt

    chosen, chosen_filter = QFileDialog.getSaveFileName(
        parent, "Ekran görüntüsünü kaydet", str(path), ";;".join(FILE_FILTERS.values()), FILE_FILTERS[fmt])
    if not chosen:
        return None
    filter_fmt = next((k for k, v in FILE_FILTERS.items() if v == chosen_filter), fmt)
    fmt = format_from_path(chosen, filter_fmt)
    path = Path(chosen)
    if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        path = path.with_name(path.name + FORMATS[fmt][1])
    settings.set("last_save_dir", str(path.parent))
    try:
        settings.save()
    except OSError:
        pass
    return path, fmt
