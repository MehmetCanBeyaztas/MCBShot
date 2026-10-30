"""Arayüz dili (Türkçe / İngilizce).

Kaynak metinler Türkçedir; tr() seçili dil İngilizceyse EN sözlüğündeki karşılığını verir.
Modül düzeyindeki sabit listelerde (araç adları vb.) metin N_() ile işaretlenir ve
gösterilirken tr() ile çevrilir. Dil program başlarken bir kez seçilir.
"""
from __future__ import annotations

import ctypes

LANGUAGES = {"auto": "Otomatik (Windows dili)", "tr": "Türkçe", "en": "English"}

_lang = "tr"


def N_(text: str) -> str:
    """Sadece işaret: metin çevrilecek ama burada değil (gösterirken tr() kullanılır)."""
    return text


def system_language() -> str:
    """Windows arayüz dili Türkçeyse 'tr', değilse 'en'."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError):
        return "en"
    return "tr" if lang_id & 0x3FF == 0x1F else "en"


def set_language(choice: str | None) -> str:
    global _lang
    _lang = choice if choice in ("tr", "en") else system_language()
    return _lang


def language() -> str:
    return _lang


def tr(text: str, **values) -> str:
    if _lang == "en":
        text = EN.get(text, text)
    return text.format(**values) if values else text


EN: dict[str, str] = {
    # ---- dil ----
    "Otomatik (Windows dili)": "Automatic (Windows language)",

    # ---- tepsi / uygulama ----
    "Ekran görüntüsü al": "Take screenshot",
    "Gecikmeli ekran görüntüsü": "Delayed screenshot",
    "Gecikmeli ekran görüntüsü ({delay} sn)": "Delayed screenshot ({delay} s)",
    "Kaydırmalı (tüm sayfa) ekran görüntüsü": "Scrolling (full page) screenshot",
    "Geçmiş…": "History…",
    "Geçmişi aç": "Open history",
    "Kayıt klasörünü aç": "Open save folder",
    "Ayarlar…": "Settings…",
    "Güncellemeleri denetle": "Check for updates",
    "Güncellemeyi yükle ({version})": "Install update ({version})",
    "Çıkış": "Quit",
    "Şu kısayollar başka bir program tarafından kullanılıyor: {keys}.":
        "These hotkeys are used by another program: {keys}.",
    " Windows'un 'Print Screen ile ekran yakalamayı aç' ayarını kapatın (README).":
        " Turn off Windows' 'Use the Print screen key to open screen capture' setting (see README).",
    " Ekran görüntüsü için şimdilik {key} kullanılıyor.": " {key} is used for screenshots for now.",
    " Ayarlar'dan değiştirebilirsiniz.": " You can change them in Settings.",
    "MCBShot çalışıyor. {key} tuşuyla ekran görüntüsü alın.": "MCBShot is running. Press {key} to take a screenshot.",
    "{app}: {delay} sn sonra ekran görüntüsü alınacak…": "{app}: taking a screenshot in {delay} s…",
    "Ekran yakalanamadı. Ayrıntılar günlük dosyasında.": "Could not capture the screen. See the log file for details.",
    "Seçili alanda yazı bulunamadı.": "No text found in the selected area.",
    "Metin panoya kopyalandı:\n{text}": "Text copied to the clipboard:\n{text}",
    " En fazla uzunluğa ulaşıldığı için durduruldu.": " Stopped because the maximum length was reached.",
    " Sayfanın bir kısmı eşleştirilemediği için orada durduruldu (sayfada hareketli içerik olabilir).":
        " Stopped where part of the page could not be matched (the page may have moving content).",
    "Uzun ekran görüntüsü hazır ({w}×{h}) ve panoya kopyalandı. Düzenleyicide açıldı.":
        "Long screenshot ready ({w}×{h}) and copied to the clipboard. Opened in the editor.",
    "Kaydedildi: {name}\nKlasörde göstermek için tıklayın.": "Saved: {name}\nClick to show it in its folder.",
    "Beklenmeyen bir hata oluştu:\n{error}\n\nAyrıntılar: {log}": "An unexpected error occurred:\n{error}\n\nDetails: {log}",
    "MCBShot zaten çalışıyor.\nSaatin yanındaki sistem tepsisinde simgesini bulabilirsiniz.":
        "MCBShot is already running.\nYou can find its icon in the system tray next to the clock.",
    "Sistem tepsisi bulunamadı.": "System tray not found.",
    "Dil değişikliği MCBShot yeniden başlatılınca uygulanır. Şimdi yeniden başlatılsın mı?":
        "The language change takes effect after MCBShot restarts. Restart now?",

    # ---- güncelleme ----
    "MCBShot güncel ({version}).": "MCBShot is up to date ({version}).",
    "Güncelleme denetlenemedi: {error}": "Could not check for updates: {error}",
    "Yeni sürüm indiriliyor: MCBShot {version}…": "Downloading the new version: MCBShot {version}…",
    "Güncelleme indirilemedi: {error}": "Could not download the update: {error}",
    "MCBShot güncellemesi": "MCBShot update",
    "MCBShot {version} hazır (şu an kullandığınız: {current}).": "MCBShot {version} is ready (you have {current}).",
    "Şimdi yükle": "Install now",
    "Sonra": "Later",
    "Sürüm sayfası": "Release page",
    "Yükleme sırasında MCBShot kapanıp birkaç saniye içinde yeniden açılır.":
        "MCBShot will close during the installation and reopen in a few seconds.",
    "MCBShot {version} sürümüne güncellendi.": "MCBShot was updated to {version}.",
    "Güncelleme başlatılamadı: {error}": "Could not start the update: {error}",
    "Yeni sürüm var: MCBShot {version}. İndirmek için tıklayın.":
        "A new version is available: MCBShot {version}. Click to download it.",
    "Sunucudan beklenmeyen yanıt": "Unexpected response from the server",
    "İndirilen dosya doğrulanamadı": "The downloaded file could not be verified",

    # ---- ayarlar ----
    "Tıklayın ve tuşa basın (yok)": "Click and press a key (none)",
    "MCBShot – Ayarlar": "MCBShot – Settings",
    "Genel": "General",
    "Kısayollar": "Hotkeys",
    "Kaydetme": "Saving",
    "Geçmiş": "History",
    "Kaydet": "Save",
    "İptal": "Cancel",
    "Varsayılanlar": "Defaults",
    "Windows açılınca MCBShot'u başlat": "Start MCBShot when Windows starts",
    "Kaydettikten sonra panoya da kopyala": "Also copy to the clipboard after saving",
    "Seçim birden fazla monitöre yayılabilsin": "Allow selections across multiple monitors",
    "Monitörlerin ölçekleri (%100, %125...) farklıysa her monitörde ayrı seçim yapılır.":
        "If the monitors use different scaling (100%, 125%...), each monitor gets its own selection.",
    " sn": " s",
    "Yok": "None",
    "Kutu (arka plan)": "Box (background)",
    "Kontur": "Outline",
    "Arayüz dili:": "Language:",
    "Güncellemeler:": "Updates:",
    "Otomatik denetle, yüklemeden önce sor": "Check automatically, ask before installing",
    "Otomatik denetle ve yükle": "Check and install automatically",
    "Kapalı": "Off",
    "Gecikmeli yakalama süresi:": "Delayed capture time:",
    "Yeni yazıların arka planı:": "Background of new text:",
    "Kutuya tıklayıp istediğiniz tuş birleşimine basın. Kaldırmak için Backspace.\n"
    "Print Screen kullanacaksanız Windows'un kendi Print Screen ayarını kapatın (README).":
        "Click a box and press the key combination you want. Backspace removes it.\n"
        "To use Print Screen, turn off Windows' own Print Screen setting (see README).",
    "Kaldır": "Clear",
    "Gözat…": "Browse…",
    "Varsayılan kayıt klasörü:": "Default save folder:",
    "Dosya adı şablonu:": "File name template:",
    "Kullanılabilir: {tarih} {saat} {yil} {ay} {gun}": "Available: {date} {time} {year} {month} {day}",
    "Örnek:": "Example:",
    "PNG (kayıpsız, önerilen)": "PNG (lossless, recommended)",
    "JPG (küçük dosya)": "JPG (small file)",
    "Format:": "Format:",
    "Kalite (JPG/WebP):": "Quality (JPG/WebP):",
    "%{value}": "{value}%",
    "Süresiz": "Forever",
    " gün": " days",
    "Sınırsız": "Unlimited",
    " görüntü": " images",
    "Şu kadar günden eskileri sil:": "Delete images older than:",
    "En fazla sakla:": "Keep at most:",
    "Geçmişte şu an {count} görüntü var. Temizlik yalnızca MCBShot'un kendi geçmiş kopyalarını siler; "
    "sizin bir klasöre kaydettiğiniz dosyalara dokunmaz.":
        "History currently holds {count} images. Cleanup only deletes MCBShot's own history copies; "
        "files you saved to a folder are never touched.",
    "Kayıt klasörünü seçin": "Choose the save folder",
    "'{text}' geçerli bir kısayol değil.": "'{text}' is not a valid hotkey.",
    "'{key}' iki işlem için birden kullanılamaz.": "'{key}' cannot be used for two actions.",
    "'{key}' kısayolu başka bir program tarafından kullanılıyor (Windows hata kodu {error}). Başka bir tuş seçin.":
        "The hotkey '{key}' is used by another program (Windows error {error}). Choose another key.",
    "Kısayol": "Hotkey",
    "Kayıt klasörü": "Save folder",
    "Bu klasör oluşturulamıyor:\n{folder}": "This folder cannot be created:\n{folder}",
    "Ayarlar": "Settings",
    "Ayarlar kaydedilemedi:\n{error}": "Settings could not be saved:\n{error}",

    # ---- seçim ekranı ----
    "Geri al (Ctrl+Z)": "Undo (Ctrl+Z)",
    "İleri al (Ctrl+Y)": "Redo (Ctrl+Y)",
    "Kaydırarak yakala – seçili alanı otomatik aşağı kaydırıp tüm sayfayı tek görüntü yapar":
        "Scrolling capture – scrolls the selected area down by itself and stitches the whole page into one image",
    "Metni kopyala – seçili alandaki yazıyı panoya alır (Ctrl+T)":
        "Copy text – copies the text in the selected area to the clipboard (Ctrl+T)",
    "Panoya kopyala (Ctrl+C)": "Copy to clipboard (Ctrl+C)",
    "Kaydet (Ctrl+S)\nHızlı kaydet: Ctrl+Shift+S": "Save (Ctrl+S)\nQuick save: Ctrl+Shift+S",
    "Kapat (Esc)": "Close (Esc)",
    "Renk kopyalandı: {color}": "Color copied: {color}",
    "Alan seçmek için sürükleyin   •   Ctrl+A: tüm ekran   •   Esc / sağ tık: iptal":
        "Drag to select an area   •   Ctrl+A: whole screen   •   Esc / right-click: cancel",
    "KAYDIRMALI YAKALAMA: kaydırılacak alanı seçin (ör. web sayfasının içerik kısmı)   •   Esc: iptal":
        "SCROLLING CAPTURE: select the area to scroll (e.g. the content part of a web page)   •   Esc: cancel",
    "Alan seçmek için sürükleyin (monitörler arasında da olur)   •   Ctrl+A: bu monitör   •   "
    "Ctrl+Shift+A: tüm monitörler   •   Esc: iptal":
        "Drag to select an area (across monitors too)   •   Ctrl+A: this monitor   •   "
        "Ctrl+Shift+A: all monitors   •   Esc: cancel",
    "C: rengi kopyala": "C: copy color",
    "Kaydedilemedi": "Could not save",

    # ---- araçlar ----
    "Seç / taşı\nNesneleri seçip taşıyın; seçimin boş yerinden sürükleyerek alanı taşıyın":
        "Select / move\nSelect and move objects; drag an empty part of the selection to move the area",
    "Kalem": "Pen",
    "Çizgi (Shift: 45° açılar)": "Line (Shift: 45° angles)",
    "Ok (Shift: 45° açılar)": "Arrow (Shift: 45° angles)",
    "Dikdörtgen (Shift: kare)": "Rectangle (Shift: square)",
    "Elips (Shift: daire)": "Ellipse (Shift: circle)",
    "Vurgulayıcı": "Highlighter",
    "Yazı (çift tık: düzenle)": "Text (double-click: edit)",
    "Numaralı adım (1, 2, 3...)": "Numbered step (1, 2, 3...)",
    "Bulanıklaştır": "Blur",
    "Pikselleştir": "Pixelate",
    "Renk": "Color",
    "Kalınlık / boyut": "Thickness / size",
    "Yazı arka planı (kutu / kontur)": "Text background (box / outline)",
    "Diğer renk…": "Other color…",
    "Renk seç": "Choose color",
    "Çok ince": "Very thin",
    "İnce": "Thin",
    "Orta": "Medium",
    "Kalın": "Thick",
    "Çok kalın": "Very thick",
    "Arka plan yok": "No background",
    "Seçili nesneyi sil (Delete)\nBir nesneyi seçmek için üzerine tıklayın":
        "Delete the selected object (Delete)\nClick an object to select it",
    "Sil": "Delete",
    "Sil ({count} nesne)": "Delete ({count} objects)",

    # ---- düzenleyici ----
    "Görüntüdeki metin": "Text in the image",
    "Tekrar kopyala": "Copy again",
    "Dosyaya kaydet (Ctrl+S)": "Save to file (Ctrl+S)",
    "Metni kopyala – görüntüdeki yazıyı panoya alır (Ctrl+T)":
        "Copy text – copies the text in the image to the clipboard (Ctrl+T)",
    "Klasörde göster": "Show in folder",
    "Kırp – tutmak istediğiniz alanı sürükleyin\n(Esc / sağ tık: vazgeç, Ctrl+Z: geri al)":
        "Crop – drag over the area you want to keep\n(Esc / right-click: cancel, Ctrl+Z: undo)",
    "Uzaklaştır (Ctrl+-, Ctrl+tekerlek)": "Zoom out (Ctrl+-, Ctrl+wheel)",
    "Yakınlaştır (Ctrl++, Ctrl+tekerlek)": "Zoom in (Ctrl++, Ctrl+wheel)",
    "Pencereye sığdır (Ctrl+0)\n%100: Ctrl+1": "Fit to window (Ctrl+0)\n100%: Ctrl+1",
    "Tutmak istediğiniz alanı sürükleyin.": "Drag over the area you want to keep.",
    "Yeniden kırp…": "Crop again…",
    "Kırpmayı kaldır (tüm görüntü)": "Remove crop (whole image)",
    "Panoya kopyalandı.": "Copied to the clipboard.",
    "Kaydedildi: {name}": "Saved: {name}",
    "Metin okunuyor…": "Reading text…",
    "Metin okunamadı": "Could not read text",
    "Görüntüde yazı bulunamadı.": "No text found in the image.",
    "Metin panoya kopyalandı ({lines} satır).": "Text copied to the clipboard ({lines} lines).",
    "Bu metin panoya kopyalandı. İsterseniz düzeltip tekrar kopyalayabilirsiniz.":
        "This text was copied to the clipboard. You can correct it and copy it again.",
    "Değişiklikler kaydedilemedi": "Changes could not be saved",

    # ---- galeri ----
    "MCBShot – Geçmiş": "MCBShot – History",
    "Ara: tarih (28.10.2026), dosya adı ya da görüntüdeki yazı…":
        "Search: date (2026-10-28), file name or text in the image…",
    "Henüz ekran görüntüsü yok.\nPrint Screen ile bir tane alıp kopyaladığınızda ya da kaydettiğinizde burada görünür.":
        "No screenshots yet.\nWhen you take one with Print Screen and copy or save it, it shows up here.",
    "Düzenle": "Edit",
    "Kopyala": "Copy",
    "Kaydet…": "Save…",
    "Çift tık: düzenle  •  Sağ tık: diğer işlemler  •  Delete: sil":
        "Double-click: edit  •  Right-click: more actions  •  Delete: delete",
    "{count} görüntü": "{count} images",
    "Geçmişten sil": "Delete from history",
    "Seçili {count} görüntü geçmişten silinsin mi?\n(Daha önce bir klasöre kaydettiğiniz dosyalar silinmez.)":
        "Delete the {count} selected images from history?\n(Files you saved to a folder are not deleted.)",

    # ---- kaydırmalı yakalama ----
    "Kaydırmalı yakalama başlıyor…": "Starting scrolling capture…",
    "Bitir (Esc)": "Finish (Esc)",
    "Kaydırılıyor…  {height} px": "Scrolling…  {height} px",

    # ---- OCR ----
    "OCR bileşeni (winrt) kurulu değil.": "The OCR component (winrt) is not installed.",
    "Bu bilgisayarda hiçbir OCR dil paketi yüklü değil.": "No OCR language pack is installed on this computer.",
    "OCR başarısız: {error}": "OCR failed: {error}",
    "Türkçe OCR dil paketi yüklü değil, İngilizce kullanıldı (Türkçe harfler hatalı olabilir). "
    "Kurmak için: Ayarlar → Saat ve dil → Dil ve bölge → Türkçe → Dil seçenekleri.":
        "The Turkish OCR language pack is not installed, English was used (Turkish letters may be wrong). "
        "To install it: Settings → Time & language → Language & region → Turkish → Language options.",

    # ---- kaydetme ----
    "PNG resmi (*.png)": "PNG image (*.png)",
    "JPG resmi (*.jpg *.jpeg)": "JPG image (*.jpg *.jpeg)",
    "WebP resmi (*.webp)": "WebP image (*.webp)",
    "Ekran görüntüsünü kaydet": "Save screenshot",
    "{format} formatı bu sistemde desteklenmiyor.": "The {format} format is not supported on this system.",
    "Dosya kaydedilemedi: {path}": "Could not save the file: {path}",
}
