"""Geçmişten açılan bir ekran görüntüsünü düzenleme penceresi.

Orijinal görüntü + kayıtlı çizimler yüklenir; oklar, yazılar vb. yeniden seçilip
değiştirilebilir. Değişiklikler pencere kapanınca (ve kopyala/kaydet/OCR'da)
geçmişe yazılır.
"""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGraphicsView, QHBoxLayout, QLabel, QMenu, QMessageBox,
                               QPlainTextEdit, QVBoxLayout, QWidget)

from .. import export, icons, ocr
from ..history import Entry, HistoryStore
from ..i18n import tr
from ..settings import Settings
from .canvas import AnnotationView
from .commands import CropCommand
from .toolbar import BAR_QSS, Bar, ToolPanel

WINDOW_QSS = """
QWidget#mcbEditor { background: #1e1f22; }
QLabel#mcbStatus { color: #bbbbbb; padding: 2px 8px; }
"""


MIN_ZOOM, MAX_ZOOM = 0.05, 16.0
BG_COLOR = QColor(45, 45, 48)
CROP_DIM = QColor(0, 0, 0, 140)


class EditorCanvas(AnnotationView):
    """Yakınlaştırılabilen, kırpılabilen tuval."""

    copyRequested = Signal()
    saveRequested = Signal(bool)   # hızlı kaydet mi
    ocrRequested = Signal()
    zoomChanged = Signal(float)    # 1.0 = %100 (1 görüntü pikseli = 1 ekran pikseli)
    cropModeChanged = Signal(bool)

    def __init__(self, image, ui_scale: float):
        super().__init__(image, ui_scale)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumSize(200, 150)
        self.fit_mode = True
        self.crop_mode = False
        self._crop_start: QPointF | None = None
        self._crop_rect: QRect | None = None
        self._pan_start = None

    # ---- yakınlaştırma ----
    def zoom(self) -> float:
        """Şu anki yakınlaştırma: 1.0 = görüntünün her pikseli ekranın bir pikseli."""
        return self.transform().m11() * self.devicePixelRatioF()

    def set_zoom(self, z: float, anchor_under_mouse: bool = False) -> None:
        z = min(max(z, MIN_ZOOM), MAX_ZOOM)
        self.fit_mode = False
        # scale() göreli çalışır ve imlecin altındaki noktayı sabit tutabilir
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if anchor_under_mouse
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        factor = z / self.zoom()
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.zoomChanged.emit(self.zoom())

    def zoom_by(self, factor: float, anchor_under_mouse: bool = False) -> None:
        self.set_zoom(self.zoom() * factor, anchor_under_mouse)

    def fit(self) -> None:
        self.fit_mode = True
        r = self.sceneRect()
        vw, vh = max(1, self.viewport().width() - 16), max(1, self.viewport().height() - 16)
        s = min(vw / max(1.0, r.width()), vh / max(1.0, r.height()), 1 / self.ui_scale)
        self.setTransform(QTransform.fromScale(s, s))
        self.zoomChanged.emit(self.zoom())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.fit_mode:
            self.fit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = e.angleDelta().y() / 120
            if steps:
                self.zoom_by(1.15 ** steps, anchor_under_mouse=True)
            e.accept()
        else:
            QGraphicsView.wheelEvent(self, e)   # normal kaydırma

    # ---- kırpma ----
    def set_crop(self, rect: QRect) -> None:
        """Görünen/dışa aktarılan alanı değiştir (CropCommand kullanır)."""
        self.edit_rect = QRect(rect)
        if not self.crop_mode:
            self.setSceneRect(QRectF(rect))
        self.resetCachedContent()
        if self.fit_mode:
            self.fit()
        self.viewport().update()

    def is_cropped(self) -> bool:
        return self.edit_rect != self.base_image.rect()

    def set_crop_mode(self, on: bool) -> None:
        if on == self.crop_mode:
            return
        self.finish_text_editing()
        self.crop_mode = on
        self._crop_start = None
        self._crop_rect = None
        # Kırparken tüm görüntü görünsün (kırpma alanı genişletilebilsin)
        self.setSceneRect(QRectF(self.base_image.rect() if on else self.edit_rect))
        self.resetCachedContent()
        if self.fit_mode:
            self.fit()
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.ArrowCursor)
        self.cropModeChanged.emit(on)
        self.viewport().update()

    def _crop_point(self, pos: QPointF) -> QPointF:
        sp = self.scene_pos(pos)
        b = self.base_image.rect()
        return QPointF(min(max(sp.x(), 0), b.width()), min(max(sp.y(), 0), b.height()))

    # ---- olaylar ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:
            self._pan_start = (e.position(), self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if self.crop_mode:
            if e.button() == Qt.MouseButton.LeftButton:
                self._crop_start = self._crop_point(e.position())
                self._crop_rect = None
            elif e.button() == Qt.MouseButton.RightButton:
                self.set_crop_mode(False)
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pan_start is not None:
            start, h, v = self._pan_start
            d = e.position() - start
            self.horizontalScrollBar().setValue(int(h - d.x()))
            self.verticalScrollBar().setValue(int(v - d.y()))
            return
        if self.crop_mode:
            if self._crop_start is not None:
                self._crop_rect = QRectF(self._crop_start, self._crop_point(e.position())).normalized().toRect()
                self.viewport().update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton and self._pan_start is not None:
            self._pan_start = None
            self.viewport().setCursor(Qt.CursorShape.CrossCursor if self.crop_mode else Qt.CursorShape.ArrowCursor)
            return
        if self.crop_mode:
            if e.button() == Qt.MouseButton.LeftButton and self._crop_start is not None:
                rect = self._crop_rect
                self._crop_start = None
                self._crop_rect = None
                self.set_crop_mode(False)
                if rect is not None and rect.width() >= 5 and rect.height() >= 5 and rect != self.edit_rect:
                    self.undo_stack.push(CropCommand(self, QRect(self.edit_rect), rect))
            return
        super().mouseReleaseEvent(e)

    def contextMenuEvent(self, e):
        if self.crop_mode:
            return
        super().contextMenuEvent(e)

    def keyPressEvent(self, e):
        if self.crop_mode and e.key() == Qt.Key.Key_Escape:
            self.set_crop_mode(False)
            return
        if self.annotation_key(e):
            self.viewport().update()
            return
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        key = e.key()
        if ctrl and key == Qt.Key.Key_C:
            self.copyRequested.emit()
        elif ctrl and key == Qt.Key.Key_S:
            self.saveRequested.emit(shift)
        elif ctrl and key == Qt.Key.Key_T:
            self.ocrRequested.emit()
        elif ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_by(1.25)
        elif ctrl and key == Qt.Key.Key_Minus:
            self.zoom_by(1 / 1.25)
        elif ctrl and key == Qt.Key.Key_0:
            self.fit()
        elif ctrl and key == Qt.Key.Key_1:
            self.set_zoom(1.0)
        else:
            super().keyPressEvent(e)

    # ---- çizim ----
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, BG_COLOR)
        area = self.base_image.rect() if self.crop_mode else self.edit_rect
        painter.drawImage(QRectF(area), self.base_image, QRectF(area))

    def drawForeground(self, painter, rect):
        if self.crop_mode:
            # Seçilmekte olan (yoksa mevcut) kırpma alanının dışını karart
            keep = self._crop_rect if self._crop_rect is not None else self.edit_rect
            outside = QPainterPath()
            outside.addRect(QRectF(self.base_image.rect()))
            inner = QPainterPath()
            inner.addRect(QRectF(keep))
            painter.fillPath(outside.subtracted(inner), CROP_DIM)
            pen = QPen(QColor("#2f8cff"), 0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(keep))
            return
        # Kırpılmış alanın dışındaki çizimler görünmesin
        outside = QPainterPath()
        outside.addRect(rect)
        inner = QPainterPath()
        inner.addRect(QRectF(self.edit_rect))
        painter.fillPath(outside.subtracted(inner), BG_COLOR)
        super().drawForeground(painter, rect)


class OcrTextDialog(QDialog):
    def __init__(self, text: str, note: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Görüntüdeki metin"))
        self.resize(520, 360)
        lay = QVBoxLayout(self)
        info = QLabel(note)
        info.setWordWrap(True)
        lay.addWidget(info)
        self.edit = QPlainTextEdit(text)
        lay.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_btn = buttons.addButton(tr("Tekrar kopyala"), QDialogButtonBox.ButtonRole.ActionRole)
        copy_btn.clicked.connect(lambda: export.copy_text(self.edit.toPlainText()))
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class EditorWindow(QWidget):
    closed = Signal(str)   # kayıt kimliği

    def __init__(self, store: HistoryStore, entry: Entry, settings: Settings):
        super().__init__(None, Qt.WindowType.Window)
        self.setObjectName("mcbEditor")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(WINDOW_QSS)
        self.setWindowIcon(icons.app_icon())
        self.store = store
        self.entry = entry
        self.settings = settings
        self._discarded = False

        self.canvas = EditorCanvas(store.original_image(entry.id), entry.scale)
        self.canvas.text_style = settings.get("text_style")
        self.canvas.load_annotations(entry.annotations)
        if entry.crop:
            self.canvas.set_crop(QRect(*entry.crop).intersected(self.canvas.base_image.rect()))
        self.canvas.undo_stack.setClean()
        self.canvas.copyRequested.connect(self.copy)
        self.canvas.saveRequested.connect(self.save)
        self.canvas.ocrRequested.connect(self.copy_text)
        self.canvas.undo_stack.cleanChanged.connect(self._update_title)
        self.canvas.undo_stack.indexChanged.connect(self._update_title)

        bar = Bar(self)
        undo_btn = bar.add_button(icons.tool_icon("undo"), tr("Geri al (Ctrl+Z)"), self.canvas.undo_stack.undo)
        redo_btn = bar.add_button(icons.tool_icon("redo"), tr("İleri al (Ctrl+Y)"), self.canvas.undo_stack.redo)
        undo_btn.setEnabled(False)
        redo_btn.setEnabled(False)
        self.canvas.undo_stack.canUndoChanged.connect(undo_btn.setEnabled)
        self.canvas.undo_stack.canRedoChanged.connect(redo_btn.setEnabled)
        self.canvas.add_delete_button(bar)
        bar.add_separator()
        bar.add_button(icons.tool_icon("copy"), tr("Panoya kopyala (Ctrl+C)"), self.copy)
        bar.add_button(icons.tool_icon("save"), tr("Dosyaya kaydet (Ctrl+S)"), lambda: self.save(False))
        bar.add_button(icons.tool_icon("ocr"), tr("Metni kopyala – görüntüdeki yazıyı panoya alır (Ctrl+T)"),
                       self.copy_text)
        bar.add_separator()
        bar.add_button(icons.tool_icon("folder"), tr("Klasörde göster"), self.show_in_folder)

        view_bar = Bar(self)
        self.crop_btn = view_bar.add_button(icons.tool_icon("crop"), tr("Kırp – tutmak istediğiniz alanı sürükleyin\n"
                                                                        "(Esc / sağ tık: vazgeç, Ctrl+Z: geri al)"),
                                            self._crop_clicked, checkable=True)
        self.canvas.cropModeChanged.connect(self.crop_btn.setChecked)
        self.canvas.cropModeChanged.connect(lambda on: None if on else self._set_status(""))
        view_bar.add_separator()
        view_bar.add_button(icons.tool_icon("zoom_out"), tr("Uzaklaştır (Ctrl+-, Ctrl+tekerlek)"),
                            lambda: self.canvas.zoom_by(1 / 1.25))
        self.zoom_label = QLabel(tr("%{value}", value=100))
        self.zoom_label.setObjectName("mcbStatus")
        self.zoom_label.setMinimumWidth(52)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        view_bar._layout.addWidget(self.zoom_label)
        view_bar.add_button(icons.tool_icon("zoom_in"), tr("Yakınlaştır (Ctrl++, Ctrl+tekerlek)"),
                            lambda: self.canvas.zoom_by(1.25))
        view_bar.add_button(icons.tool_icon("fit"), tr("Pencereye sığdır (Ctrl+0)\n%100: Ctrl+1"), self.canvas.fit)
        self.canvas.zoomChanged.connect(lambda z: self.zoom_label.setText(tr("%{value}", value=round(z * 100))))

        self.status = QLabel("")
        self.status.setObjectName("mcbStatus")

        top = QHBoxLayout()
        top.setContentsMargins(8, 8, 8, 0)
        top.addWidget(bar)
        top.addWidget(view_bar)
        top.addStretch(1)
        top.addWidget(self.status)
        middle = QHBoxLayout()
        middle.setContentsMargins(8, 8, 8, 8)
        middle.setSpacing(8)
        middle.addWidget(ToolPanel(self, self.canvas), 0, Qt.AlignmentFlag.AlignTop)
        middle.addWidget(self.canvas, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addLayout(top)
        root.addLayout(middle, 1)

        self._update_title()
        self._initial_size()

    def _initial_size(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        img = self.canvas.base_image
        w = img.width() / self.entry.scale + 90
        h = img.height() / self.entry.scale + 90
        self.resize(QSize(int(min(max(w, 640), screen.width() * 0.85)),
                          int(min(max(h, 420), screen.height() * 0.85))))

    def _update_title(self, *_):
        star = "" if self.canvas.undo_stack.isClean() else " •"
        r = self.canvas.edit_rect
        self.setWindowTitle(f"MCBShot – {self.entry.display_date()} ({r.width()}×{r.height()}){star}")

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    def _crop_clicked(self) -> None:
        if self.canvas.crop_mode:
            self.canvas.set_crop_mode(False)
            return
        if not self.canvas.is_cropped():
            self.canvas.set_crop_mode(True)
            self._set_status(tr("Tutmak istediğiniz alanı sürükleyin."))
            return
        # Zaten kırpılmış: yeniden kırp ya da kırpmayı kaldır
        self.crop_btn.setChecked(False)
        menu = QMenu(self)
        menu.setStyleSheet(BAR_QSS)
        menu.addAction(tr("Yeniden kırp…")).triggered.connect(lambda: self.canvas.set_crop_mode(True))
        menu.addAction(tr("Kırpmayı kaldır (tüm görüntü)")).triggered.connect(self._uncrop)
        menu.exec(self.crop_btn.mapToGlobal(self.crop_btn.rect().bottomLeft()))

    def _uncrop(self) -> None:
        full = self.canvas.base_image.rect()
        self.canvas.undo_stack.push(CropCommand(self.canvas, QRect(self.canvas.edit_rect), full, "Kırpmayı kaldır"))

    def _crop_value(self) -> list[int] | None:
        r = self.canvas.edit_rect
        return [r.x(), r.y(), r.width(), r.height()] if self.canvas.is_cropped() else None

    # ---- işlemler ----
    def persist(self) -> None:
        """Çizimleri ve kırpmayı geçmişe yaz (değişiklik varsa)."""
        if self._discarded or self.canvas.undo_stack.isClean() and not self.canvas._editing_text:
            return
        states = self.canvas.annotation_states()
        crop = self._crop_value()
        if states == self.entry.annotations and crop == self.entry.crop:
            self.canvas.undo_stack.setClean()
            return
        self.store.update(self.entry.id, states, self.canvas.render_image(), crop)
        self.entry.annotations = states
        self.entry.crop = crop
        self.canvas.undo_stack.setClean()

    def copy(self) -> None:
        self.persist()
        export.copy_image(self.canvas.render_image())
        self._set_status(tr("Panoya kopyalandı."))

    def save(self, quick: bool = False) -> None:
        self.persist()
        target = export.choose_save_target(self, self.settings, quick, suggested=self.entry.saved_path)
        if target is None:
            return
        path, fmt = target
        image = self.canvas.render_image()
        try:
            export.save_image(image, path, fmt, self.settings.get("quality"))
        except OSError as ex:
            QMessageBox.warning(self, tr("Kaydedilemedi"), str(ex))
            return
        if self.settings.get("copy_after_save"):
            export.copy_image(image)
        self.entry.saved_path = str(path)
        self.store.set_saved_path(self.entry.id, str(path))
        self._set_status(tr("Kaydedildi: {name}", name=path.name))

    def copy_text(self) -> None:
        self.persist()
        self._set_status(tr("Metin okunuyor…"))
        self.setCursor(Qt.CursorShape.BusyCursor)
        ocr.recognize_async(self.canvas.render_image(), self._on_ocr_done)

    def _on_ocr_done(self, result, error) -> None:
        self.unsetCursor()
        if error:
            self._set_status("")
            QMessageBox.warning(self, tr("Metin okunamadı"), error)
            return
        text = result.text.strip()
        if not text:
            self._set_status(tr("Görüntüde yazı bulunamadı."))
            return
        export.copy_text(text)
        self.store.set_ocr_text(self.entry.id, text)
        lines = text.count("\n") + 1
        self._set_status(tr("Metin panoya kopyalandı ({lines} satır).", lines=lines))
        note = tr("Bu metin panoya kopyalandı. İsterseniz düzeltip tekrar kopyalayabilirsiniz.")
        if result.fallback:
            note = tr(ocr.FALLBACK_HINT) + "\n\n" + note
        OcrTextDialog(text, note, self).exec()

    def show_in_folder(self) -> None:
        self.persist()
        path = self.entry.saved_path
        if not path or not os.path.exists(path):
            path = str(self.store.original_path(self.entry.id))
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')

    def discard(self) -> None:
        """Kayıt geçmişten silindi: değişiklikleri yazmadan kapan."""
        self._discarded = True
        self.close()

    def closeEvent(self, e):
        try:
            self.persist()
        except OSError as ex:
            QMessageBox.warning(self, tr("Değişiklikler kaydedilemedi"), str(ex))
        self.closed.emit(self.entry.id)
        super().closeEvent(e)
