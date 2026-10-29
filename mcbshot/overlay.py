"""Alan seçme katmanı (her monitör için bir tam ekran pencere) ve araç çubukları.

Seçim her zaman FİZİKSEL piksel cinsinden tutulur (self.psel). Ekrana çizerken
mantıksal piksele çevrilir. Böylece ekranda gördüğünüz alan ile kaydedilen alan
farklı ölçekli monitörlerde bile piksel piksel aynıdır.

Katman bir AnnotationView'dir: seçim yapıldıktan sonra aynı pencerede çizim
araçları (ok, yazı, bulanıklaştırma...) kullanılır.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from enum import Enum, auto

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMessageBox

from . import export, icons
from .capture import ScreenShot
from .editor import AnnotationView
from .editor.toolbar import Bar, ToolPanel
from .history import HistoryStore
from .settings import Settings

log = logging.getLogger("MCBShot")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.SetWindowPos.restype = wintypes.BOOL
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
_ARROW_KEYS = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}

DIM_COLOR = QColor(0, 0, 0, 110)
ACCENT = QColor("#2f8cff")
HANDLE_SIZE = 7.0        # tutamaç kenarı (mantıksal px)
HANDLE_HIT = 7.0         # tutamaç yakalama mesafesi
MIN_SELECTION = 3        # bundan küçük seçimler tıklama sayılır (fiziksel px)
MAG_CELLS = 15           # büyüteçte gösterilen piksel sayısı (tek sayı)
MAG_SIZE = 120           # büyüteç kutusu (mantıksal px)
MAG_INFO_H = 52

_HANDLE_CURSORS = {
    "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
    "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
    "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
    "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
    "move": Qt.CursorShape.SizeAllCursor,
}


class Mode(Enum):
    IDLE = auto()        # henüz seçim yok
    SELECTING = auto()   # fareyle sürükleniyor
    SELECTED = auto()    # seçim tamam, araç çubukları görünür


class SelectionOverlay(AnnotationView):
    selectionStarted = Signal(object)      # self
    copyRequested = Signal(object)         # self
    saveRequested = Signal(object, bool)   # self, hızlı kaydet mi
    ocrRequested = Signal(object)          # self
    scrollRequested = Signal(object)       # self
    cancelRequested = Signal()

    def __init__(self, shot: ScreenShot):
        super().__init__(shot.image, shot.dpr)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.shot = shot
        self.dpr = shot.dpr
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

        self.mode = Mode.IDLE
        self.scroll_mode = False          # seçim biter bitmez kaydırmalı yakalama başlasın
        self.psel = QRect()               # seçim, fiziksel piksel
        self._anchor = QPoint()
        self._press = QPoint()
        self._orig = QRect()
        self._drag: str | None = None     # seçim için: "move" veya tutamaç adı
        self._cursor_pos: QPointF | None = None
        self._flash = ""                  # kısa süreli bilgi mesajı (ör. renk kopyalandı)
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(1600)
        self._flash_timer.timeout.connect(self._clear_flash)

        self.tool_panel = ToolPanel(self.viewport(), self)
        self.tool_panel.hide()
        self.action_bar = Bar(self.viewport())
        undo_btn = self.action_bar.add_button(icons.tool_icon("undo"), "Geri al (Ctrl+Z)", self.undo_stack.undo)
        redo_btn = self.action_bar.add_button(icons.tool_icon("redo"), "İleri al (Ctrl+Y)", self.undo_stack.redo)
        undo_btn.setEnabled(False)
        redo_btn.setEnabled(False)
        self.undo_stack.canUndoChanged.connect(undo_btn.setEnabled)
        self.undo_stack.canRedoChanged.connect(redo_btn.setEnabled)
        self.add_delete_button(self.action_bar)
        self.action_bar.add_separator()
        self.action_bar.add_button(icons.tool_icon("scroll"), "Kaydırarak yakala – seçili alanı otomatik aşağı "
                                   "kaydırıp tüm sayfayı tek görüntü yapar", lambda: self.scrollRequested.emit(self))
        self.action_bar.add_button(icons.tool_icon("ocr"), "Metni kopyala – seçili alandaki yazıyı panoya alır (Ctrl+T)",
                                   lambda: self.ocrRequested.emit(self))
        self.action_bar.add_button(icons.tool_icon("copy"), "Panoya kopyala (Ctrl+C)",
                                   lambda: self.copyRequested.emit(self))
        self.action_bar.add_button(icons.tool_icon("save"), "Kaydet (Ctrl+S)\nHızlı kaydet: Ctrl+Shift+S",
                                   lambda: self.saveRequested.emit(self, False))
        self.action_bar.add_separator()
        self.action_bar.add_button(icons.tool_icon("close"), "Kapat (Esc)", self.cancelRequested.emit)
        self.action_bar.hide()

        # Pencereyi doğru monitöre yerleştir (DPI'ı o monitörden alsın)
        self.winId()
        self.windowHandle().setScreen(shot.screen)
        if shot.spans:
            geom = shot.screens[0].geometry()
            for s in shot.screens[1:]:
                geom = geom.united(s.geometry())
            self.setGeometry(geom)   # yaklaşık; asıl konum show() sonrası apply_native_geometry ile
        else:
            self.setGeometry(shot.screen.geometry())

    def apply_native_geometry(self) -> None:
        """Birden çok monitörü kaplayan pencereyi fiziksel piksel olarak tam yerine oturt."""
        if not self.shot.spans:
            return
        r = self.shot.physical
        _user32.SetWindowPos(int(self.winId()), None, r.x(), r.y(), r.width(), r.height(),
                             SWP_NOZORDER | SWP_NOACTIVATE)

    # ---- monitör alanları (pencere içi mantıksal koordinat) ----
    def _screen_rect_at(self, pos: QPointF) -> QRectF:
        """pos noktasının bulunduğu monitörün dikdörtgeni; hiçbirinde değilse en yakını."""
        rects = [self._to_logical(r) for r in self.shot.screen_rects]
        for r in rects:
            if r.contains(pos):
                return r

        def distance(r: QRectF) -> float:
            dx = max(r.left() - pos.x(), 0, pos.x() - r.right())
            dy = max(r.top() - pos.y(), 0, pos.y() - r.bottom())
            return dx * dx + dy * dy
        return min(rects, key=distance)

    def _clear_flash(self) -> None:
        self._flash = ""
        self.viewport().update()

    # seçim = tuvalin çizim/dışa aktarma alanı
    @property
    def psel(self) -> QRect:
        return self.edit_rect

    @psel.setter
    def psel(self, r: QRect) -> None:
        self.edit_rect = QRect(r)

    # ---- koordinat dönüşümleri ----
    def _to_phys(self, pos: QPointF) -> QPoint:
        img = self.shot.image
        x = min(max(int(pos.x() * self.dpr), 0), img.width() - 1)
        y = min(max(int(pos.y() * self.dpr), 0), img.height() - 1)
        return QPoint(x, y)

    def _to_logical(self, r: QRect) -> QRectF:
        d = self.dpr
        return QRectF(r.x() / d, r.y() / d, r.width() / d, r.height() / d)

    # ---- dışarıdan kullanılanlar ----
    def selected_image(self) -> QImage:
        return self.render_image()

    def history_payload(self) -> tuple[QImage, list[dict], float]:
        """Geçmiş için: çizimsiz kırpılmış görüntü, seçime göreli çizimler, ölçek."""
        original = self.shot.image.copy(self.psel)
        original.setDevicePixelRatio(1.0)
        return original, self.annotation_states(self.psel.topLeft()), self.dpr

    def reset_selection(self) -> None:
        self.mode = Mode.IDLE
        self.psel = QRect()
        self._drag = None
        self._hide_bars()
        self.viewport().update()

    def select_all(self, all_screens: bool = False) -> None:
        """Ctrl+A: imlecin olduğu monitör. Ctrl+Shift+A: bütün monitörler."""
        self.selectionStarted.emit(self)
        if all_screens or not self.shot.spans:
            self.psel = self.shot.image.rect()
        else:
            pos = self._cursor_pos or QPointF(self.mapFromGlobal(QCursor.pos()))
            r = self._screen_rect_at(pos)
            self.psel = next(sr for sr in self.shot.screen_rects if self._to_logical(sr) == r)
        self.mode = Mode.SELECTED
        self._place_bars()
        self.viewport().update()

    # ---- seçim yardımcıları ----
    @staticmethod
    def _handle_points(r: QRectF) -> dict[str, QPointF]:
        cx, cy = r.center().x(), r.center().y()
        return {
            "tl": r.topLeft(), "t": QPointF(cx, r.top()), "tr": r.topRight(),
            "r": QPointF(r.right(), cy), "br": r.bottomRight(), "b": QPointF(cx, r.bottom()),
            "bl": r.bottomLeft(), "l": QPointF(r.left(), cy),
        }

    def _hit_test(self, pos: QPointF) -> str | None:
        if self.mode != Mode.SELECTED or self.psel.isEmpty():
            return None
        r = self._to_logical(self.psel)
        for name, pt in self._handle_points(r).items():
            if abs(pos.x() - pt.x()) <= HANDLE_HIT and abs(pos.y() - pt.y()) <= HANDLE_HIT:
                return name
        return "move" if r.contains(pos) else None

    def _apply_drag(self, pt: QPoint) -> None:
        bounds = self.shot.image.rect()
        d = pt - self._press
        o = self._orig
        if self._drag == "move":
            x = min(max(o.x() + d.x(), 0), bounds.width() - o.width())
            y = min(max(o.y() + d.y(), 0), bounds.height() - o.height())
            self.psel = QRect(x, y, o.width(), o.height())
            return
        left, top, right, bottom = o.left(), o.top(), o.right(), o.bottom()
        if "l" in self._drag:
            left += d.x()
        if "r" in self._drag:
            right += d.x()
        if "t" in self._drag:
            top += d.y()
        if "b" in self._drag:
            bottom += d.y()
        self.psel = QRect(QPoint(min(left, right), min(top, bottom)),
                          QPoint(max(left, right), max(top, bottom))).intersected(bounds)

    def _hide_bars(self) -> None:
        self.tool_panel.hide()
        self.action_bar.hide()

    def _place_bars(self) -> None:
        """Araç çubuklarını seçimin yanına koy; her zaman görünen bir monitörün içinde kalsınlar."""
        r = self._to_logical(self.psel)
        m = 6

        def clamp(v, lo, hi):
            return min(max(v, lo), max(lo, hi))

        # İşlem çubuğu: seçimin altında, sağa yaslı
        ab = self.action_bar
        ab.adjustSize()
        w, h = ab.width(), ab.height()
        c = self._screen_rect_at(QPointF(r.right() - 1, r.bottom() - 1))
        x = clamp(r.right() - w, c.left() + m, c.right() - w - m)
        y = r.bottom() + m
        if y + h > c.bottom() - m:          # altta yer yok -> üste
            y = r.top() - h - m
        if y < c.top() + m:                 # üstte de yok -> seçimin içine
            y = r.bottom() - h - m
        y = clamp(y, c.top() + m, c.bottom() - h - m)
        ab.move(int(x), int(y))

        # Araç paneli: seçimin sağında, yoksa solunda, yoksa içinde
        tp = self.tool_panel
        tp.adjustSize()
        w, h = tp.width(), tp.height()
        c = self._screen_rect_at(QPointF(r.right() - 1, r.top()))
        x = r.right() + m
        if x + w > c.right() - m:
            x = r.left() - w - m
            if x < c.left() + m:
                x = r.right() - w - m
        x = clamp(x, c.left() + m, c.right() - w - m)
        y = clamp(r.top(), c.top() + m, c.bottom() - h - m)
        tp.move(int(x), int(y))

        tp.show()
        ab.show()
        tp.raise_()
        ab.raise_()

    def _update_cursor(self, pos: QPointF) -> None:
        cursor = None
        if self.mode == Mode.SELECTED:
            hit = self._hit_test(pos)
            if hit and hit != "move":
                cursor = _HANDLE_CURSORS[hit]
            else:
                cursor = self.annotation_cursor(pos)
                if cursor is None and hit == "move" and self.tool == "select":
                    cursor = _HANDLE_CURSORS["move"]
        self.viewport().setCursor(cursor if cursor is not None else Qt.CursorShape.CrossCursor)

    # ---- olaylar ----
    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() == Qt.MouseButton.RightButton:
            # Sağ tık: seçim varsa temizle (çizim yoksa), seçim yoksa tamamen çık
            if self.mode == Mode.SELECTED:
                if not self.annotations():
                    self.reset_selection()
            else:
                self.cancelRequested.emit()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.activateWindow()

        if self.mode == Mode.SELECTED:
            # 1) seçili nesnenin tutamacı
            if self.annotation_handle_at(pos):
                self.annotation_press(e)
                self.viewport().update()
                return
            # 2) seçim alanının tutamacı
            hit = self._hit_test(pos)
            if hit and hit != "move":
                self._start_selection_drag(hit, pos)
                return
            # 3) çizim aracı / nesne seçme
            if self.annotation_press(e):
                self.viewport().update()
                return
            # 4) seçim alanını taşı
            if hit == "move":
                self._start_selection_drag(hit, pos)
                return
            # 5) çizim varken dışarıya tıklamak yeni seçim başlatmasın
            if self.annotations():
                self.viewport().update()
                return

        self.selectionStarted.emit(self)
        self.mode = Mode.SELECTING
        pt = self._to_phys(pos)
        self._anchor = pt
        self.psel = QRect(pt, pt)
        self._hide_bars()
        self.viewport().update()

    def _start_selection_drag(self, hit: str, pos: QPointF) -> None:
        self._drag = hit
        self._press = self._to_phys(pos)
        self._orig = QRect(self.psel)
        self._hide_bars()

    def mouseMoveEvent(self, e):
        pos = e.position()
        self._cursor_pos = pos
        pt = self._to_phys(pos)
        if self.mode == Mode.SELECTING:
            a = self._anchor
            self.psel = QRect(QPoint(min(a.x(), pt.x()), min(a.y(), pt.y())),
                              QPoint(max(a.x(), pt.x()), max(a.y(), pt.y())))
        elif self._drag:
            self._apply_drag(pt)
        elif not self.annotation_move(e):
            self._update_cursor(pos)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.annotation_release(e):
            self.viewport().update()
            return
        if self.mode == Mode.SELECTING:
            if self.psel.width() < MIN_SELECTION or self.psel.height() < MIN_SELECTION:
                self.reset_selection()
                return
            self.mode = Mode.SELECTED
            if self.scroll_mode:
                self.scrollRequested.emit(self)
                return
        self._drag = None
        if self.mode == Mode.SELECTED:
            self._place_bars()
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.mode != Mode.SELECTED:
            return
        if self.annotation_double_click(e):
            self.viewport().update()
            return
        # Seçimin boş bir yerine çift tık (Seç aracında): kopyala ve kapat
        if self.tool == "select" and self._hit_test(e.position()) == "move":
            self.copyRequested.emit(self)

    def viewportEvent(self, e):
        if e.type() == QEvent.Type.Leave:
            self._cursor_pos = None
            self.viewport().update()
        return super().viewportEvent(e)

    def keyPressEvent(self, e):
        if self.annotation_key(e):
            self.viewport().update()
            return
        key = e.key()
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if key == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
        elif ctrl and key == Qt.Key.Key_A:
            self.select_all(all_screens=shift)
        elif key == Qt.Key.Key_C and not ctrl and self._cursor_pos is not None:
            self._copy_color(rgb=shift)
        elif self.mode != Mode.SELECTED:
            return
        elif key in _ARROW_KEYS and self._drag is None:
            # Ok tuşları: seçim alanını 1 px (Shift: 10 px) kaydır
            dx, dy = _ARROW_KEYS[key]
            step = 10 if shift else 1
            b = self.shot.image.rect()
            r = self.psel.translated(dx * step, dy * step)
            r.moveTo(min(max(r.x(), 0), b.width() - r.width()), min(max(r.y(), 0), b.height() - r.height()))
            self.psel = r
            self._place_bars()
            self.viewport().update()
        elif (ctrl and key == Qt.Key.Key_C) or key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.copyRequested.emit(self)
        elif ctrl and key == Qt.Key.Key_S:
            self.saveRequested.emit(self, shift)
        elif ctrl and key == Qt.Key.Key_T:
            self.ocrRequested.emit(self)

    def _copy_color(self, rgb: bool = False) -> None:
        """İmlecin altındaki pikselin rengini panoya kopyala (C: #RRGGBB, Shift+C: rgb(...))."""
        c = self.shot.image.pixelColor(self._to_phys(self._cursor_pos))
        text = f"rgb({c.red()}, {c.green()}, {c.blue()})" if rgb else c.name().upper()
        export.copy_text(text)
        self._flash = f"Renk kopyalandı: {text}"
        self._flash_timer.start()
        self.viewport().update()

    # ---- çizim ----
    def drawForeground(self, painter, rect):
        p = painter
        p.save()
        p.resetTransform()   # buradan sonra koordinatlar = pencere (mantıksal px)
        full = QRectF(0, 0, self.viewport().width(), self.viewport().height())
        has_sel = self.mode != Mode.IDLE and not self.psel.isEmpty()
        if has_sel:
            r = self._to_logical(self.psel)
            outside = QPainterPath()
            outside.addRect(full)
            inner = QPainterPath()
            inner.addRect(r)
            p.fillPath(outside.subtracted(inner), DIM_COLOR)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pen = QPen(ACCENT, 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r.adjusted(-0.5, -0.5, 0.5, 0.5))
            if self.mode == Mode.SELECTED:
                self._paint_handles(p, r)
                p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                self.paint_annotation_overlay(p)
            self._paint_size_label(p, r)
        else:
            p.fillRect(full, DIM_COLOR)
            if self._cursor_pos is not None:
                self._paint_hint(p)
        if self._cursor_pos is not None and (self.mode != Mode.SELECTED or self._drag not in (None, "move")):
            self._paint_magnifier(p)
        if self._flash and self._cursor_pos is not None:
            p.setFont(self._label_font(9))
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(self._flash) + 20, fm.height() + 10
            c = self._screen_rect_at(self._cursor_pos)
            x = min(self._cursor_pos.x() + 16, c.right() - w - 4)
            y = max(self._cursor_pos.y() - h - 12, c.top() + 4)
            self._paint_box_text(p, QRectF(x, y, w, h), self._flash)
        p.restore()

    def _paint_handles(self, p: QPainter, r: QRectF) -> None:
        p.setPen(QPen(QColor("white"), 1))
        p.setBrush(ACCENT)
        s = HANDLE_SIZE
        for pt in self._handle_points(r).values():
            p.drawRect(QRectF(pt.x() - s / 2, pt.y() - s / 2, s, s))

    def _label_font(self, size: float = 9.0) -> QFont:
        f = QFont(self.font())
        f.setPointSizeF(size)
        return f

    def _paint_box_text(self, p: QPainter, box: QRectF, text: str, align=Qt.AlignmentFlag.AlignCenter) -> None:
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 200))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("white"))
        p.drawText(box.adjusted(6, 0, -6, 0), align, text)
        p.restore()

    def _paint_size_label(self, p: QPainter, r: QRectF) -> None:
        text = f"{self.psel.width()} × {self.psel.height()}"
        p.setFont(self._label_font())
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 14, fm.height() + 6
        x, y = r.left(), r.top() - h - 4
        if y < self._screen_rect_at(r.topLeft()).top():
            x, y = r.left() + 4, r.top() + 4
        self._paint_box_text(p, QRectF(x, y, w, h), text)

    def _paint_hint(self, p: QPainter) -> None:
        text = "Alan seçmek için sürükleyin   •   Ctrl+A: tüm ekran   •   Esc / sağ tık: iptal"
        if self.scroll_mode:
            text = ("KAYDIRMALI YAKALAMA: kaydırılacak alanı seçin (ör. web sayfasının içerik kısmı)   •   "
                    "Esc: iptal")
        elif self.shot.spans:
            text = ("Alan seçmek için sürükleyin (monitörler arasında da olur)   •   "
                    "Ctrl+A: bu monitör   •   Ctrl+Shift+A: tüm monitörler   •   Esc: iptal")
        p.setFont(self._label_font(10))
        fm = p.fontMetrics()
        w, h = fm.horizontalAdvance(text) + 24, fm.height() + 12
        c = self._screen_rect_at(self._cursor_pos)
        self._paint_box_text(p, QRectF(c.left() + (c.width() - w) / 2, c.top() + 24, w, h), text)

    def _paint_magnifier(self, p: QPainter) -> None:
        pos = self._cursor_pos
        img = self.shot.image
        c = self._to_phys(pos)
        n, half = MAG_CELLS, MAG_CELLS // 2

        # İmlecin etrafındaki n×n fiziksel pikseli al (ekran kenarında siyahla doldur)
        src = QRect(c.x() - half, c.y() - half, n, n)
        patch = QImage(n, n, QImage.Format.Format_RGB32)
        patch.fill(QColor(0, 0, 0))
        valid = src.intersected(img.rect())
        if not valid.isEmpty():
            pp = QPainter(patch)
            pp.drawImage(valid.topLeft() - src.topLeft(), img, valid)
            pp.end()

        size = MAG_SIZE
        screen = self._screen_rect_at(pos)
        x, y = pos.x() + 20, pos.y() + 20
        if x + size > screen.right():
            x = pos.x() - 20 - size
        if y + size + MAG_INFO_H > screen.bottom():
            y = pos.y() - 20 - size - MAG_INFO_H
        box = QRectF(x, y, size, size)
        cell = size / n

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        p.drawImage(box, patch)
        p.setPen(QPen(QColor(255, 255, 255, 28), 0))
        for i in range(1, n):
            p.drawLine(QPointF(x + i * cell, y), QPointF(x + i * cell, y + size))
            p.drawLine(QPointF(x, y + i * cell), QPointF(x + size, y + i * cell))
        p.setPen(QPen(QColor("white"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x + half * cell, y + half * cell, cell, cell))
        p.setPen(QPen(ACCENT, 2))
        p.drawRect(box)

        color = img.pixelColor(c)
        info = QRectF(x, y + size, size, MAG_INFO_H)
        p.fillRect(info, QColor(0, 0, 0, 215))
        p.fillRect(QRectF(info.right() - 22, info.top() + 8, 16, 16), color)
        p.setPen(QColor("white"))
        p.setFont(self._label_font(8))
        p.drawText(info.adjusted(6, 0, -26, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"X: {c.x()}  Y: {c.y()}\n{color.name().upper()}\nC: rengi kopyala")
        p.restore()


class CaptureSession(QObject):
    """Bir yakalama işlemi: tüm monitörlerdeki katmanları yönetir."""

    finished = Signal()
    saved = Signal(str)                    # kaydedilen dosya yolu
    recorded = Signal(str, QImage)         # geçmişe eklendi: kimlik, orijinal görüntü
    ocrRequested = Signal(QImage, str)     # okunacak görüntü, geçmiş kimliği ("" olabilir)
    scrollRequested = Signal(QRect, QRect, float)  # alan (fiziksel), aynı alan (mantıksal, global), ölçek

    def __init__(self, shots: list[ScreenShot], settings: Settings, history: HistoryStore | None = None,
                 parent: QObject | None = None, scroll_mode: bool = False):
        super().__init__(parent)
        self.scroll_mode = scroll_mode
        self.settings = settings
        self.history = history
        self._closed = False
        self.overlays: list[SelectionOverlay] = []
        for shot in shots:
            ov = SelectionOverlay(shot)
            ov.text_style = settings.get("text_style")
            ov.selectionStarted.connect(self._on_selection_started)
            ov.copyRequested.connect(self._copy)
            ov.saveRequested.connect(self._save)
            ov.ocrRequested.connect(self._ocr)
            ov.scrollRequested.connect(self._scroll)
            ov.cancelRequested.connect(self.close)
            ov.scroll_mode = scroll_mode
            self.overlays.append(ov)

    def start(self) -> None:
        for ov in self.overlays:
            ov.show()
            ov.apply_native_geometry()
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor)
        target = next((o for o in self.overlays if screen in o.shot.screens), self.overlays[0])
        for ov in self.overlays:
            local = QPointF(ov.mapFromGlobal(cursor))
            if ov.rect().contains(local.toPoint()):
                ov._cursor_pos = local
        target.raise_()
        target.activateWindow()
        target.setFocus()

    def _on_selection_started(self, source: SelectionOverlay) -> None:
        # Aynı anda tek monitörde seçim olabilir
        for ov in self.overlays:
            if ov is not source and ov.mode != Mode.IDLE:
                ov.reset_selection()

    def _record(self, ov: SelectionOverlay, rendered: QImage, saved_path: str | None = None) -> str:
        """Geçmişe ekle. Hata olursa sessizce geç (asıl işi engellemesin)."""
        if self.history is None:
            return ""
        try:
            original, states, scale = ov.history_payload()
            entry_id = self.history.add(original, states, rendered, scale, saved_path)
        except Exception:
            log.exception("Geçmişe eklenemedi")
            return ""
        self.recorded.emit(entry_id, original)
        return entry_id

    def _copy(self, ov: SelectionOverlay) -> None:
        image = ov.selected_image()
        export.copy_image(image)
        self._record(ov, image)
        self.close()

    def _scroll(self, ov: SelectionOverlay) -> None:
        physical = ov.psel.translated(ov.shot.physical.topLeft())
        r = ov._to_logical(ov.psel)
        top_left = ov.mapToGlobal(r.topLeft().toPoint())
        logical = QRect(top_left, r.size().toSize())
        dpr = ov.dpr
        self.close()
        self.scrollRequested.emit(physical, logical, dpr)

    def _ocr(self, ov: SelectionOverlay) -> None:
        image = ov.selected_image()
        original, states, scale = ov.history_payload()
        entry_id = ""
        if self.history is not None:
            try:
                entry_id = self.history.add(original, states, image, scale)
            except Exception:
                log.exception("Geçmişe eklenemedi")
        self.close()
        self.ocrRequested.emit(image, entry_id)

    def _save(self, ov: SelectionOverlay, quick: bool) -> None:
        target = export.choose_save_target(ov, self.settings, quick)
        if target is None:
            return  # vazgeçildi, seçim ekranında kal
        path, fmt = target
        image = ov.selected_image()
        try:
            export.save_image(image, path, fmt, self.settings.get("quality"))
        except OSError as ex:
            QMessageBox.warning(ov, "Kaydedilemedi", str(ex))
            return
        if self.settings.get("copy_after_save"):
            export.copy_image(image)
        self._record(ov, image, str(path))
        self.saved.emit(str(path))
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for ov in self.overlays:
            ov.close()
        self.overlays.clear()
        self.finished.emit()

