"""Görüntüdeki yazıyı okuma: Windows'un yerleşik OCR motoru (Windows.Media.Ocr).

Türkçe arayüzde: Türkçe dil paketi yoksa İngilizceye, o da yoksa kullanıcının profil diline düşer.
İngilizce arayüzde önce kullanıcının Windows'taki dilleri, sonra İngilizce kullanılır.
OCR arka plan iş parçacığında çalışır; arayüz donmaz.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage

from . import i18n
from .i18n import N_, tr

log = logging.getLogger("MCBShot")

PREFERRED_LANGS = ("tr", "en-US", "en")


@dataclass
class OcrResult:
    text: str
    language: str          # kullanılan dil (ör. "tr")
    fallback: bool         # Türkçe arayüzde Türkçe yerine başka dile düşüldü mü


class OcrUnavailable(RuntimeError):
    pass


def _make_engine():
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
    except ImportError as ex:
        raise OcrUnavailable(tr("OCR bileşeni (winrt) kurulu değil.")) from ex
    if i18n.language() != "tr":
        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is not None:
            return engine
    for tag in PREFERRED_LANGS:
        lang = Language(tag)
        if OcrEngine.is_language_supported(lang):
            engine = OcrEngine.try_create_from_language(lang)
            if engine is not None:
                return engine
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable(tr("Bu bilgisayarda hiçbir OCR dil paketi yüklü değil."))
    return engine


def _prepare(image: QImage, max_dim: int) -> QImage:
    img = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    # Küçük yazılar büyütülünce daha iyi okunur
    if max(img.width(), img.height()) < 1600:
        img = img.scaled(img.width() * 2, img.height() * 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    if max(img.width(), img.height()) > max_dim:
        img = img.scaled(max_dim, max_dim, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    return img


def recognize(image: QImage) -> OcrResult:
    """Senkron OCR. Arayüz iş parçacığında DEĞİL, arka planda çağırın."""
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter

    engine = _make_engine()
    img = _prepare(image, OcrEngine.max_image_dimension)
    writer = DataWriter()
    writer.write_bytes(bytes(img.constBits()))
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, img.width(), img.height(), BitmapAlphaMode.PREMULTIPLIED)

    async def run():
        return await engine.recognize_async(bitmap)

    result = asyncio.run(run())
    text = "\n".join(line.text for line in result.lines)
    lang = engine.recognizer_language.language_tag
    return OcrResult(text=text, language=lang,
                     fallback=i18n.language() == "tr" and not lang.lower().startswith("tr"))


class _Signals(QObject):
    done = Signal(object, object)   # (OcrResult | None, hata mesajı | None)


class _OcrTask(QRunnable):
    def __init__(self, image: QImage, signals: _Signals):
        super().__init__()
        self.image = QImage(image)
        self.signals = signals

    def run(self):
        try:
            self.signals.done.emit(recognize(self.image), None)
        except OcrUnavailable as ex:
            self.signals.done.emit(None, str(ex))
        except Exception as ex:   # OCR hiçbir zaman uygulamayı çökertmesin
            log.exception("OCR hatası")
            self.signals.done.emit(None, tr("OCR başarısız: {error}", error=ex))


_active: set[_Signals] = set()


def recognize_async(image: QImage, callback) -> None:
    """OCR'ı arka planda çalıştırır; bitince callback(result, error) arayüz iş parçacığında çağrılır."""
    signals = _Signals()
    _active.add(signals)

    def finished(result, error):
        _active.discard(signals)
        callback(result, error)

    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(_OcrTask(image, signals))


# Gösterirken tr() ile çevrilir
FALLBACK_HINT = N_("Türkçe OCR dil paketi yüklü değil, İngilizce kullanıldı (Türkçe harfler hatalı olabilir). "
                   "Kurmak için: Ayarlar → Saat ve dil → Dil ve bölge → Türkçe → Dil seçenekleri.")
