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
from .i18n import LANGUAGES, tr
from .settings import DEFAULTS, HOTKEYS, UPDATE_MODES, Settings

_MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta, Qt.Key.Key_AltGr}


class HotkeyEdit(QLineEdit):
    """Tıklayıp tuşa basarak kısayol atanan kutu. Backspace/Delete: kısayolu kaldır."""

    def __init__(self, text: str = ""):
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText(tr("Tıklayın ve tuşa basın (yok)"))
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
        self.setWindowTitle(tr("MCBShot – Ayarlar"))
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(560)
        self.settings = settings
        self.test_hotkey = test_hotkey

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), tr("Genel"))
        tabs.addTab(self._hotkey_tab(), tr("Kısayollar"))
        tabs.addTab(self._save_tab(), tr("Kaydetme"))
        tabs.addTab(self._history_tab(history_count), tr("Geçmiş"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Kaydet"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("İptal"))
        defaults_btn = buttons.addButton(tr("Varsayılanlar"), QDialogButtonBox.ButtonRole.ResetRole)
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
        self.start_with_windows = QCheckBox(tr("Windows açılınca MCBShot'u başlat"))
        self.copy_after_save = QCheckBox(tr("Kaydettikten sonra panoya da kopyala"))
        self.span_monitors = QCheckBox(tr("Seçim birden fazla monitöre yayılabilsin"))
        self.span_monitors.setToolTip(tr("Monitörlerin ölçekleri (%100, %125...) farklıysa her monitörde ayrı "
                                         "seçim yapılır."))
        self.delay = QSpinBox()
        self.delay.setRange(1, 30)
        self.delay.setSuffix(tr(" sn"))
        self.text_style = QComboBox()
        for key, label in (("none", tr("Yok")), ("box", tr("Kutu (arka plan)")), ("glow", tr("Kontur"))):
            self.text_style.addItem(label, key)
        self.language = QComboBox()
        for key, label in LANGUAGES.items():
            self.language.addItem(tr(label), key)
        self.update_mode = QComboBox()
        for key, label in UPDATE_MODES.items():
            self.update_mode.addItem(tr(label), key)
        form.addRow(self.start_with_windows)
        form.addRow(self.copy_after_save)
        form.addRow(self.span_monitors)
        form.addRow(tr("Gecikmeli yakalama süresi:"), self.delay)
        form.addRow(tr("Yeni yazıların arka planı:"), self.text_style)
        form.addRow(tr("Arayüz dili:"), self.language)
        form.addRow(tr("Güncellemeler:"), self.update_mode)
        return w

    def _hotkey_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        info = QLabel(tr("Kutuya tıklayıp istediğiniz tuş birleşimine basın. Kaldırmak için Backspace.\n"
                         "Print Screen kullanacaksanız Windows'un kendi Print Screen ayarını kapatın (README)."))
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.hotkey_edits: dict[str, HotkeyEdit] = {}
        for name, (key, label) in HOTKEYS.items():
            edit = HotkeyEdit()
            clear = QPushButton(tr("Kaldır"))
            clear.clicked.connect(lambda checked=False, e=edit: (setattr(e, "hotkey", ""), e._show()))
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(clear)
            form.addRow(tr(label) + ":", row)
            self.hotkey_edits[name] = edit
        lay.addLayout(form)
        lay.addStretch(1)
        return w

    def _save_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.save_dir = QLineEdit()
        browse = QPushButton(tr("Gözat…"))
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.save_dir, 1)
        row.addWidget(browse)
        form.addRow(tr("Varsayılan kayıt klasörü:"), row)

        self.template = QLineEdit()
        self.template.textChanged.connect(self._update_preview)
        form.addRow(tr("Dosya adı şablonu:"), self.template)
        hint = QLabel(tr("Kullanılabilir: {tarih} {saat} {yil} {ay} {gun}"))
        hint.setStyleSheet("color: gray")
        form.addRow("", hint)
        self.preview = QLabel()
        form.addRow(tr("Örnek:"), self.preview)

        self.format = QComboBox()
        for key, label in (("png", tr("PNG (kayıpsız, önerilen)")), ("jpg", tr("JPG (küçük dosya)")),
                           ("webp", "WebP")):
            self.format.addItem(label, key)
        self.format.currentIndexChanged.connect(self._update_quality_enabled)
        self.format.currentIndexChanged.connect(self._update_preview)
        form.addRow(tr("Format:"), self.format)

        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(1, 100)
        self.quality_label = QLabel()
        self.quality.valueChanged.connect(lambda v: self.quality_label.setText(tr("%{value}", value=v)))
        qrow = QHBoxLayout()
        qrow.addWidget(self.quality, 1)
        qrow.addWidget(self.quality_label)
        form.addRow(tr("Kalite (JPG/WebP):"), qrow)
        return w

    def _history_tab(self, count: int) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.keep_days = QSpinBox()
        self.keep_days.setRange(0, 3650)
        self.keep_days.setSpecialValueText(tr("Süresiz"))
        self.keep_days.setSuffix(tr(" gün"))
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 100000)
        self.max_items.setSpecialValueText(tr("Sınırsız"))
        self.max_items.setSuffix(tr(" görüntü"))
        form.addRow(tr("Şu kadar günden eskileri sil:"), self.keep_days)
        form.addRow(tr("En fazla sakla:"), self.max_items)
        note = QLabel(tr("Geçmişte şu an {count} görüntü var. Temizlik yalnızca MCBShot'un kendi geçmiş "
                         "kopyalarını siler; sizin bir klasöre kaydettiğiniz dosyalara dokunmaz.", count=count))
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
        self.language.setCurrentIndex(max(0, self.language.findData(data.get("language", "auto"))))
        self.update_mode.setCurrentIndex(max(0, self.update_mode.findData(data.get("update_mode", "ask"))))
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
        folder = QFileDialog.getExistingDirectory(self, tr("Kayıt klasörünü seçin"), self.save_dir.text())
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
                return tr("'{text}' geçerli bir kısayol değil.", text=text)
            if key in seen:
                return tr("'{key}' iki işlem için birden kullanılamaz.", key=describe_hotkey(text))
            seen[key] = name
            if self.test_hotkey is not None:
                ok, err = self.test_hotkey(text)
                if not ok:
                    return tr("'{key}' kısayolu başka bir program tarafından kullanılıyor (Windows hata kodu "
                              "{error}). Başka bir tuş seçin.", key=describe_hotkey(text), error=err)
        return None

    def accept(self) -> None:
        error = self._validate_hotkeys()
        if error:
            QMessageBox.warning(self, tr("Kısayol"), error)
            return
        folder = self.save_dir.text().strip()
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError:
            QMessageBox.warning(self, tr("Kayıt klasörü"), tr("Bu klasör oluşturulamıyor:\n{folder}", folder=folder))
            return
        s = self.settings
        s.set("start_with_windows", self.start_with_windows.isChecked())
        s.set("copy_after_save", self.copy_after_save.isChecked())
        s.set("span_monitors", self.span_monitors.isChecked())
        s.set("delay_seconds", self.delay.value())
        s.set("text_style", self.text_style.currentData())
        s.set("language", self.language.currentData())
        s.set("update_mode", self.update_mode.currentData())
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
            QMessageBox.warning(self, tr("Ayarlar"), tr("Ayarlar kaydedilemedi:\n{error}", error=ex))
            return
        super().accept()
