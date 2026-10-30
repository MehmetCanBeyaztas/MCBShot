"""Ayarların okunması/yazılması (%APPDATA%\\MCBShot\\settings.json) ve Windows ile başlatma."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import APP_NAME
from .i18n import N_


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_save_dir() -> str:
    return str(Path.home() / "Pictures" / APP_NAME)


# Kısayol adı -> (ayar anahtarı, açıklama; gösterirken tr() ile çevrilir)
HOTKEYS = {
    "capture": ("hotkey_capture", N_("Ekran görüntüsü al")),
    "delayed": ("hotkey_delayed", N_("Gecikmeli ekran görüntüsü")),
    "scroll": ("hotkey_scroll", N_("Kaydırmalı (tüm sayfa) ekran görüntüsü")),
    "history": ("hotkey_history", N_("Geçmişi aç")),
}

UPDATE_MODES = {
    "ask": N_("Otomatik denetle, yüklemeden önce sor"),
    "auto": N_("Otomatik denetle ve yükle"),
    "off": N_("Kapalı"),
}

DEFAULTS: dict = {
    "hotkey_capture": "Print",
    "hotkey_delayed": "Shift+Print",
    "hotkey_scroll": "Ctrl+Print",
    "hotkey_history": "",
    "save_dir": default_save_dir(),
    "last_save_dir": "",
    "filename_template": "MCBShot_{tarih}_{saat}",
    "format": "png",          # png | jpg | webp
    "quality": 90,            # jpg / webp için 1-100
    "copy_after_save": False,
    "start_with_windows": False,
    "delay_seconds": 3,
    "span_monitors": True,    # seçim monitörler arasında yayılabilsin
    "history_keep_days": 0,   # 0 = süresiz sakla
    "history_max_items": 0,   # 0 = sınırsız
    "text_style": "none",     # yazı arka planı: none | box | glow
    "language": "auto",       # auto | tr | en
    "update_mode": "ask",     # ask | auto | off
    "last_version": "",       # güncellemeden sonra "güncellendi" bildirimi için
}


class Settings:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else app_data_dir() / "settings.json"
        self.data: dict = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self.data.update(stored)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Bozuk dosya: varsayılanlarla devam et, kullanıcı kaydettiğinde düzelir.
            pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, key: str):
        return self.data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value) -> None:
        self.data[key] = value


# ---- Windows ile başlat (HKCU\...\Run) ----
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    """Windows açılışında çalıştırılacak komut (.exe ya da pythonw + run.py)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(sys.executable)
    script = Path(__file__).resolve().parent.parent / "run.py"
    return f'"{pythonw}" "{script}"'


def get_autostart(name: str = APP_NAME) -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def set_autostart(enabled: bool, name: str = APP_NAME) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass
