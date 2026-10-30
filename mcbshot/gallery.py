"""Geçmiş galerisi: küçük resimler, tarih, arama ve işlemler."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from . import export, icons
from .editor.canvas import render_annotated
from .history import Entry, HistoryStore
from .i18n import tr
from .settings import Settings

GALLERY_QSS = """
QWidget#mcbGallery { background: #1e1f22; color: #e6e6e6; }
QLineEdit { background: #2b2d31; color: #f0f0f0; border: 1px solid #444; border-radius: 6px; padding: 7px 10px; }
QLineEdit:focus { border-color: #2f8cff; }
QListWidget { background: #1e1f22; border: none; color: #d8d8d8; outline: none; }
QListWidget::item { border-radius: 6px; padding: 6px; }
QListWidget::item:hover { background: #2b2d31; }
QListWidget::item:selected { background: #24456f; color: white; }
QPushButton { background: #2b2d31; color: #eee; border: 1px solid #444; border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background: #34373c; }
QPushButton:disabled { color: #777; }
QLabel#mcbCount { color: #9a9a9a; }
QLabel#mcbEmpty { color: #8a8a8a; font-size: 14px; }
QMenu { background: #2a2b2e; color: #eeeeee; border: 1px solid #555; padding: 4px; }
QMenu::item { padding: 5px 18px 5px 10px; }
QMenu::item:selected { background: #2f8cff; }
"""

ID_ROLE = Qt.ItemDataRole.UserRole
ICON_SIZE = QSize(240, 150)


class GalleryWindow(QWidget):
    openRequested = Signal(str)   # kayıt kimliği

    def __init__(self, store: HistoryStore, settings: Settings):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("mcbGallery")
        self.setWindowTitle(tr("MCBShot – Geçmiş"))
        self.setWindowIcon(icons.app_icon())
        self.setStyleSheet(GALLERY_QSS)
        self.resize(1000, 680)
        self.store = store
        self.settings = settings
        self._entries: dict[str, Entry] = {}
        self._icon_cache: dict[str, tuple[float, QIcon]] = {}

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Ara: tarih (28.10.2026), dosya adı ya da görüntüdeki yazı…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        self.count_label = QLabel()
        self.count_label.setObjectName("mcbCount")
        self.count_label.setMinimumWidth(110)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(ICON_SIZE)
        self.list.setGridSize(QSize(262, 210))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setWordWrap(True)
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemActivated.connect(lambda item: self.openRequested.emit(item.data(ID_ROLE)))
        self.list.itemSelectionChanged.connect(self._update_buttons)

        self.empty_label = QLabel(tr("Henüz ekran görüntüsü yok.\nPrint Screen ile bir tane alıp kopyaladığınızda "
                                     "ya da kaydettiğinizde burada görünür."))
        self.empty_label.setObjectName("mcbEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_open = QPushButton(tr("Düzenle"))
        self.btn_copy = QPushButton(tr("Kopyala"))
        self.btn_save = QPushButton(tr("Kaydet…"))
        self.btn_folder = QPushButton(tr("Klasörde göster"))
        self.btn_delete = QPushButton(tr("Sil"))
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_copy.clicked.connect(self._copy_selected)
        self.btn_save.clicked.connect(self._save_selected)
        self.btn_folder.clicked.connect(self._folder_selected)
        self.btn_delete.clicked.connect(self._delete_selected)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.count_label)
        buttons = QHBoxLayout()
        for b in (self.btn_open, self.btn_copy, self.btn_save, self.btn_folder):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_delete)
        hint = QLabel(tr("Çift tık: düzenle  •  Sağ tık: diğer işlemler  •  Delete: sil"))
        hint.setObjectName("mcbCount")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)
        root.addLayout(top)
        root.addWidget(self.list, 1)
        root.addWidget(self.empty_label, 1)
        root.addWidget(hint)
        root.addLayout(buttons)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(150)
        self._refresh_timer.timeout.connect(self.refresh)
        store.changed.connect(self._refresh_timer.start)
        self.refresh()

    # ---- liste ----
    def _icon_for(self, entry: Entry) -> QIcon:
        path = self.store.thumb_path(entry.id)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return QIcon()
        cached = self._icon_cache.get(entry.id)
        if cached and cached[0] == mtime:
            return cached[1]
        # Tüm küçük resimler aynı kutuda ortalansın: alt yazılar hizalı kalır
        thumb = QPixmap(str(path)).scaled(ICON_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
        canvas = QPixmap(ICON_SIZE)
        canvas.fill(Qt.GlobalColor.transparent)
        p = QPainter(canvas)
        p.drawPixmap((ICON_SIZE.width() - thumb.width()) // 2, (ICON_SIZE.height() - thumb.height()) // 2, thumb)
        p.end()
        icon = QIcon(canvas)
        self._icon_cache[entry.id] = (mtime, icon)
        return icon

    def refresh(self) -> None:
        selected = set(self._selected_ids())
        entries = self.store.entries()
        self._entries = {e.id: e for e in entries}
        self.list.clear()
        for e in entries:
            name = os.path.basename(e.saved_path) if e.saved_path else ""
            w, h = e.display_size()
            item = QListWidgetItem(self._icon_for(e), f"{e.display_date()}\n{w} × {h}")
            item.setData(ID_ROLE, e.id)
            item.setToolTip(f"{e.display_date()}  •  {w}×{h}" + (f"\n{name}" if name else ""))
            self.list.addItem(item)
            if e.id in selected:
                item.setSelected(True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self.search.text().strip()
        shown = 0
        for i in range(self.list.count()):
            item = self.list.item(i)
            entry = self._entries.get(item.data(ID_ROLE))
            visible = entry is not None and entry.matches(query)
            item.setHidden(not visible)
            shown += visible
        total = self.list.count()
        self.count_label.setText(f"{shown} / {total}" if query else tr("{count} görüntü", count=total))
        self.list.setVisible(total > 0)
        self.empty_label.setVisible(total == 0)
        self._update_buttons()

    def _selected_ids(self) -> list[str]:
        return [item.data(ID_ROLE) for item in self.list.selectedItems() if not item.isHidden()]

    def _update_buttons(self) -> None:
        n = len(self._selected_ids())
        for b in (self.btn_open, self.btn_copy, self.btn_save, self.btn_folder):
            b.setEnabled(n == 1)
        self.btn_delete.setEnabled(n > 0)

    def _context_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        if not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        single = len(self._selected_ids()) == 1
        menu = QMenu(self)
        for text, slot, enabled in ((tr("Düzenle"), self._open_selected, single),
                                    (tr("Kopyala"), self._copy_selected, single),
                                    (tr("Kaydet…"), self._save_selected, single),
                                    (tr("Klasörde göster"), self._folder_selected, single)):
            act = menu.addAction(text)
            act.setEnabled(enabled)
            act.triggered.connect(slot)
        menu.addSeparator()
        menu.addAction(tr("Sil")).triggered.connect(self._delete_selected)
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete and self._selected_ids():
            self._delete_selected()
        elif e.key() == Qt.Key.Key_C and e.modifiers() & Qt.KeyboardModifier.ControlModifier and not self.search.hasFocus():
            self._copy_selected()
        else:
            super().keyPressEvent(e)

    # ---- işlemler ----
    def _single(self) -> Entry | None:
        ids = self._selected_ids()
        return self._entries.get(ids[0]) if len(ids) == 1 else None

    def _rendered(self, entry: Entry):
        return render_annotated(self.store.original_image(entry.id), entry.annotations, entry.crop)

    def _open_selected(self) -> None:
        entry = self._single()
        if entry:
            self.openRequested.emit(entry.id)

    def _copy_selected(self) -> None:
        entry = self._single()
        if entry:
            export.copy_image(self._rendered(entry))

    def _save_selected(self) -> None:
        entry = self._single()
        if not entry:
            return
        target = export.choose_save_target(self, self.settings, False, suggested=entry.saved_path)
        if target is None:
            return
        path, fmt = target
        try:
            export.save_image(self._rendered(entry), path, fmt, self.settings.get("quality"))
        except OSError as ex:
            QMessageBox.warning(self, tr("Kaydedilemedi"), str(ex))
            return
        self.store.set_saved_path(entry.id, str(path))

    def _folder_selected(self) -> None:
        entry = self._single()
        if not entry:
            return
        path = entry.saved_path
        if not path or not os.path.exists(path):
            path = str(self.store.original_path(entry.id))
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')

    def _delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        answer = QMessageBox.question(
            self, tr("Geçmişten sil"),
            tr("Seçili {count} görüntü geçmişten silinsin mi?\n"
               "(Daha önce bir klasöre kaydettiğiniz dosyalar silinmez.)", count=len(ids)))
        if answer != QMessageBox.StandardButton.Yes:
            return
        for entry_id in ids:
            self.store.delete(entry_id)
            self._icon_cache.pop(entry_id, None)
