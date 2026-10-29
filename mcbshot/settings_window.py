"""Ayarlar penceresi."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from . import export, icons
from .hotkey import describe_hotkey, key_name_for_vk, parse_hotkey
from .settings import DEFAULTS, HOTKEYS, Settings

_MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr}


class HotkeyEdit(QLineEdit):
    """Tıklayıp tuşa basarak kısayol atanan kutu. Backspace/Delete: kısayolu kaldır."""

    def __init__(self, text: str = ""):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("Tıklayın ve tuşa basın (yok)")
        self.hotkey = text
        self._show()

    def _show(self) -> None:
        self.setText(describe_hotkey(self.hotkey) if self.hotkey else "")

    def _accept(self, e) -> None:
        name = key_name_for_vk(e.nativeVirtualKey())
        if name is None:
            return
        mods = e.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        # Tek başına harf/rakam her yazıda tetiklenirdi: en az bir değiştirici iste
        if not parts and (len(name) == 1 or name == "Space"):
            return
        self.hotkey = "+".join(parts + [name])
        self._show()

    def keyPressEvent(self, e):
        if e.key() in _MODIFIER_KEYS:
            return
        if e.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete) and not e.modifiers():
            self.hotkey = ""
            self._show()
            return
        if e.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Escape):
            super().keyPressEvent(e)
            return
        self._accept(e)

    def keyReleaseEvent(self, e):
        # Windows, Print Screen için çoğu zaman sadece "bırakma" olayı gönderir
        if e.key() == Qt.Key.Key_Print or e.nativeVirtualKey() == 0x2C:
            self._accept(e)


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, test_hotkey=None, parent=None, history_count: int = 0):
        """test_hotkey(text) -> (başarılı mı, hata kodu): kısayolun Windows'a kaydedilebildiğini sınar."""
        super().__init__(parent)
        self.setWindowTitle("MCBShot – Ayarlar")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(560)
        self.settings = settings
        self.test_hotkey = test_hotkey

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "Genel")
        tabs.addTab(self._hotkey_tab(), "Kısayollar")
        tabs.addTab(self._save_tab(), "Kaydetme")
        tabs.addTab(self._history_tab(history_count), "Geçmiş")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        defaults_btn = buttons.addButton("Varsayılanlar", QDialogButtonBox.ButtonRole.ResetRole)
        defaults_btn.clicked.connect(self._reset_defaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addWidget(tabs)
        root.addWidget(buttons)
        self._load(settings.data)

    # ---- sekmeler ----
    def _general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.start_with_windows = QCheckBox("Windows açılınca MCBShot'u başlat")
        self.copy_after_save = QCheckBox("Kaydettikten sonra panoya da kopyala")
        self.span_monitors = QCheckBox("Seçim birden fazla monitöre yayılabilsin")
        self.span_monitors.setToolTip("Monitörlerin ölçekleri (%100, %125...) farklıysa her monitörde ayrı seçim yapılır.")
        self.delay = QSpinBox()
        self.delay.setRange(1, 30)
        self.delay.setSuffix(" sn")
        self.text_style = QComboBox()
        for key, label in (("none", "Yok"), ("box", "Kutu (arka plan)"), ("glow", "Kontur")):
            self.text_style.addItem(label, key)
        form.addRow(self.start_with_windows)
        form.addRow(self.copy_after_save)
        form.addRow(self.span_monitors)
        form.addRow("Gecikmeli yakalama süresi:", self.delay)
        form.addRow("Yeni yazıların arka planı:", self.text_style)
        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel("Kutuya tıklayıp istediğiniz tuş birleşimine basın. Kaldırmak için Backspace.\n"
                      "Print Screen kullanacaksanız Windows'un kendi Print Screen ayarını kapatın (README).")
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.hotkey_edits: dict[str, HotkeyEdit] = {}
        for name, (key, label) in HOTKEYS.items():
            edit = HotkeyEdit()
            clear = QPushButton("Kaldır")
            clear.clicked.connect(lambda checked=False, e=edit: (setattr(e, "hotkey", ""), e._show()))
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(clear)
            form.addRow(label + ":", row)
            self.hotkey_edits[name] = edit
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _save_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.save_dir = QLineEdit()
        browse = QPushButton("Gözat…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.save_dir, 1)
        row.addWidget(browse)
        form.addRow("Varsayılan kayıt klasörü:", row)

        self.template = QLineEdit()
        self.template.textChanged.connect(self._update_preview)
        form.addRow("Dosya adı şablonu:", self.template)
        hint = QLabel("Kullanılabilir: {tarih} {saat} {yil} {ay} {gun}")
        hint.setStyleSheet("color: gray")
        form.addRow("", hint)
        self.preview = QLabel()
        form.addRow("Örnek:", self.preview)

        self.format = QComboBox()
        for key, label in (("png", "PNG (kayıpsız, önerilen)"), ("jpg", "JPG (küçük dosya)"), ("webp", "WebP")):
            self.format.addItem(label, key)
        self.format.currentIndexChanged.connect(self._update_quality_enabled)
        self.format.currentIndexChanged.connect(self._update_preview)
        form.addRow("Format:", self.format)

        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(1, 100)
        self.quality_label = QLabel()
        self.quality.valueChanged.connect(lambda v: self.quality_label.setText(f"%{v}"))
        qrow = QHBoxLayout()
        qrow.addWidget(self.quality, 1)
        qrow.addWidget(self.quality_label)
        form.addRow("Kalite (JPG/WebP):", qrow)
        return w

    def _history_tab(self, count: int) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.keep_days = QSpinBox()
        self.keep_days.setRange(0, 3650)
        self.keep_days.setSpecialValueText("Süresiz")
        self.keep_days.setSuffix(" gün")
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 100000)
        self.max_items.setSpecialValueText("Sınırsız")
        self.max_items.setSuffix(" görüntü")
        form.addRow("Şu kadar günden eskileri sil:", self.keep_days)
        form.addRow("En fazla sakla:", self.max_items)
        note = QLabel(f"Geçmişte şu an {count} görüntü var. Temizlik yalnızca MCBShot'un kendi geçmiş "
                      "kopyalarını siler; sizin bir klasöre kaydettiğiniz dosyalara dokunmaz.")
        note.setWordWrap(True)
        form.addRow(note)
        return w

    # ---- yardımcılar ----
    def _load(self, data: dict) -> None:
        self.start_with_windows.setChecked(bool(data.get("start_with_windows")))
        self.copy_after_save.setChecked(bool(data.get("copy_after_save")))
        self.span_monitors.setChecked(bool(data.get("span_monitors", True)))
        self.delay.setValue(int(data.get("delay_seconds", 3)))
        self.text_style.setCurrentIndex(max(0, self.text_style.findData(data.get("text_style", "none"))))
        for name, (key, _) in HOTKEYS.items():
            self.hotkey_edits[name].hotkey = data.get(key, "") or ""
            self.hotkey_edits[name]._show()
        self.save_dir.setText(data.get("save_dir", ""))
        self.template.setText(data.get("filename_template", ""))
        self.format.setCurrentIndex(max(0, self.format.findData(data.get("format", "png"))))
        self.quality.setValue(int(data.get("quality", 90)))
        self.keep_days.setValue(int(data.get("history_keep_days", 0)))
        self.max_items.setValue(int(data.get("history_max_items", 0)))
        self._update_quality_enabled()
        self._update_preview()

    def _reset_defaults(self) -> None:
        self._load(dict(DEFAULTS))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Kayıt klasörünü seçin", self.save_dir.text())
        if folder:
            self.save_dir.setText(str(Path(folder)))

    def _update_quality_enabled(self) -> None:
        self.quality.setEnabled(self.format.currentData() != "png")

    def _update_preview(self) -> None:
        ext = export.FORMATS.get(self.format.currentData(), ("", ".png"))[1]
        self.preview.setText(export.render_filename(self.template.text() or "{tarih}", datetime.now()) + ext)

    def _validate_hotkeys(self) -> str | None:
        seen = {}
        for name, edit in self.hotkey_edits.items():
            text = edit.hotkey
            if not text:
                continue
            try:
                key = parse_hotkey(text)
            except ValueError:
                return f"'{text}' geçerli bir kısayol değil."
            if key in seen:
                return f"'{describe_hotkey(text)}' iki işlem için birden kullanılamaz."
            seen[key] = name
            if self.test_hotkey is not None:
                ok, err = self.test_hotkey(text)
                if not ok:
                    return (f"'{describe_hotkey(text)}' kısayolu başka bir program tarafından kullanılıyor "
                            f"(Windows hata kodu {err}). Başka bir tuş seçin.")
        return None

    def accept(self) -> None:
        error = self._validate_hotkeys()
        if error:
            QMessageBox.warning(self, "Kısayol", error)
            return
        folder = self.save_dir.text().strip()
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError:
            QMessageBox.warning(self, "Kayıt klasörü", f"Bu klasör oluşturulamıyor:\n{folder}")
            return
        s = self.settings
        s.set("start_with_windows", self.start_with_windows.isChecked())
        s.set("copy_after_save", self.copy_after_save.isChecked())
        s.set("span_monitors", self.span_monitors.isChecked())
        s.set("delay_seconds", self.delay.value())
        s.set("text_style", self.text_style.currentData())
        for name, (key, _) in HOTKEYS.items():
            s.set(key, self.hotkey_edits[name].hotkey)
        s.set("save_dir", folder)
        s.set("filename_template", self.template.text().strip() or DEFAULTS["filename_template"])
        s.set("format", self.format.currentData())
        s.set("quality", self.quality.value())
        s.set("history_keep_days", self.keep_days.value())
        s.set("history_max_items", self.max_items.value())
        try:
            s.save()
        except OSError as ex:
            QMessageBox.warning(self, "Ayarlar", f"Ayarlar kaydedilemedi:\n{ex}")
            return
        super().accept()
