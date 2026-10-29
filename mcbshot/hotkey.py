"""Global kısayollar: Windows RegisterHotKey API'si (ctypes ile).

Yönetici izni gerektirmez. Mesajlar gizli bir Qt penceresine (HWND) gelir ve
nativeEvent içinde yakalanır.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_SPECIAL_KEYS = {
    "print": 0x2C, "prtsc": 0x2C, "printscreen": 0x2C,
    "space": 0x20, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22, "pause": 0x13, "scrolllock": 0x91,
    "esc": 0x1B, "escape": 0x1B,
}


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Shift+X' veya 'Print' gibi bir metni (modifiers, virtual-key) çiftine çevirir."""
    mods = 0
    vk = None
    for part in text.replace(" ", "").split("+"):
        p = part.lower()
        if not p:
            continue
        if p in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif p == "alt":
            mods |= MOD_ALT
        elif p == "shift":
            mods |= MOD_SHIFT
        elif p in ("win", "meta"):
            mods |= MOD_WIN
        elif p in _SPECIAL_KEYS:
            vk = _SPECIAL_KEYS[p]
        elif len(p) == 1 and p.isascii() and p.isalnum():
            vk = ord(p.upper())
        elif p[0] == "f" and p[1:].isdigit() and 1 <= int(p[1:]) <= 24:
            vk = 0x70 + int(p[1:]) - 1
        else:
            raise ValueError(f"Bilinmeyen tuş: {part}")
    if vk is None:
        raise ValueError("Kısayolda ana tuş yok")
    return mods, vk


_VK_NAMES = {0x2C: "Print", 0x20: "Space", 0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End",
             0x21: "PageUp", 0x22: "PageDown", 0x13: "Pause", 0x91: "ScrollLock"}


def key_name_for_vk(vk: int) -> str | None:
    """Windows sanal tuş kodu -> kısayol metnindeki tuş adı (klavye düzeninden bağımsız)."""
    if 0x41 <= vk <= 0x5A or 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x70 <= vk <= 0x87:
        return f"F{vk - 0x6F}"
    return _VK_NAMES.get(vk)


def describe_hotkey(text: str) -> str:
    """Menüde gösterilecek kısa ad (Print -> PrtSc)."""
    return "+".join("PrtSc" if p.lower() in ("print", "printscreen") else p
                    for p in text.replace(" ", "").split("+"))


class HotkeyManager(QWidget):
    """Hiç gösterilmeyen, sadece WM_HOTKEY mesajlarını almak için var olan pencere."""

    activated = Signal(str)  # kısayolun adı (örn. "capture")

    def __init__(self):
        super().__init__()
        self._hwnd = int(self.winId())
        self._ids: dict[str, int] = {}
        self._names: dict[int, str] = {}
        self._next_id = 1

    def register(self, name: str, text: str) -> tuple[bool, int]:
        """Başarılıysa (True, 0), değilse (False, Windows hata kodu) döner."""
        self.unregister(name)
        try:
            mods, vk = parse_hotkey(text)
        except ValueError:
            return False, -1
        hid = self._next_id
        self._next_id += 1
        if not _user32.RegisterHotKey(self._hwnd, hid, mods | MOD_NOREPEAT, vk):
            return False, ctypes.get_last_error()
        self._ids[name] = hid
        self._names[hid] = name
        return True, 0

    def unregister(self, name: str) -> None:
        hid = self._ids.pop(name, None)
        if hid is not None:
            self._names.pop(hid, None)
            _user32.UnregisterHotKey(self._hwnd, hid)

    def unregister_all(self) -> None:
        for name in list(self._ids):
            self.unregister(name)

    def nativeEvent(self, eventType, message):
        et = eventType.data() if hasattr(eventType, "data") else eventType
        if et == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                name = self._names.get(int(msg.wParam))
                if name:
                    # Ağır işi (ekran yakalama, pencere açma) mesaj işleyicisinin dışında yap.
                    QTimer.singleShot(0, lambda n=name: self.activated.emit(n))
                    return True, 0
        return super().nativeEvent(eventType, message)
