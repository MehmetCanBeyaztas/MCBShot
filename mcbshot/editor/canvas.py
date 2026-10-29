"""Çizim tuvali: bir görüntü + üzerindeki nesneler (QGraphicsScene).

Hem yakalama ekranı (overlay) hem de 3. aşamadaki düzenleyici penceresi bunu
kullanır. Sahne birimi = görüntünün fiziksel pikseli; görünüm 1/ui_scale ile
küçültülür, böylece High-DPI ekranda 1 görüntü pikseli = 1 ekran pikseli olur.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform, QUndoStack
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView, QMenu

from .. import icons
from .commands import AddItemsCommand, RemoveItemsCommand, StateCommand
from .items import (ArrowItem, CensorItem, EllipseItem, LineItem, PenItem, RectItem, StepItem, TextItem,
                    is_annotation, item_from_state, size_for, snap_45)
from .toolbar import BAR_QSS

TOOLS = ("select", "pen", "line", "arrow", "rect", "ellipse", "highlighter", "text", "step", "blur", "pixelate")
DEFAULT_COLOR = "#ff3b30"
DEFAULT_HIGHLIGHT = "#ffd60a"
ACCENT = QColor("#2f8cff")
ITEM_HANDLE = 7.0     # nesne tutamacı (mantıksal px)
ITEM_HANDLE_HIT = 7.0
CLICK_DISTANCE = 4.0  # bundan az fare hareketi "tıklama" sayılır (mantıksal px)
_ARROWS = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}


def render_annotated(image: QImage, states: list[dict], crop: list[int] | None = None) -> QImage:
    """Pencere açmadan: görüntü + JSON'daki çizimler (+ kırpma) -> tek görüntü (galeriden kopyalama için)."""
    full = _render_full(image, states)
    if crop:
        return full.copy(QRect(*crop))
    return full


def _render_full(image: QImage, states: list[dict]) -> QImage:
    scene = QGraphicsScene()
    scene.setSceneRect(QRectF(image.rect()))
    items = []
    for z, state in enumerate(states):
        try:
            item = item_from_state(state, image)
        except (KeyError, ValueError, TypeError):
            continue
        item.setZValue(z)
        scene.addItem(item)
        items.append(item)
    out = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(out)
    p.drawImage(QPointF(0, 0), image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    scene.render(p, QRectF(out.rect()), QRectF(image.rect()))
    p.end()
    for item in items:
        scene.removeItem(item)
    return out.convertToFormat(QImage.Format.Format_RGB32)


class AnnotationView(QGraphicsView):
    toolChanged = Signal(str)
    styleChanged = Signal()

    def __init__(self, base_image: QImage, ui_scale: float = 1.0, parent=None):
        super().__init__(parent)
        self.base_image = base_image
        self.ui_scale = ui_scale

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(QRectF(base_image.rect()))
        self.setScene(self._scene)
        self.setSceneRect(QRectF(base_image.rect()))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setTransform(QTransform.fromScale(1 / ui_scale, 1 / ui_scale))

        self.edit_rect = QRect(base_image.rect())   # çizim yapılabilen / dışa aktarılan alan
        self.undo_stack = QUndoStack(self)
        self.tool = "select"
        self.colors = {"default": QColor(DEFAULT_COLOR), "highlighter": QColor(DEFAULT_HIGHLIGHT)}
        self.level = 1
        self.text_style = "none"

        self._z = 0
        self._draw_item = None
        self._draw_origin = QPointF()
        self._draw_press_pos = QPointF()   # çizime başlanan nokta (görünüm koordinatı)
        self._handle_drag = None           # (nesne, tutamaç adı)
        self._press_snapshot = None        # taşıma öncesi durumlar
        self._editing_text: TextItem | None = None

        self._scene.selectionChanged.connect(self.viewport().update)

    def add_delete_button(self, bar) -> None:
        """Bir araç çubuğuna 'seçili nesneyi sil' düğmesi ekler (seçim yokken pasif)."""
        btn = bar.add_button(icons.tool_icon("delete"), "Seçili nesneyi sil (Delete)\n"
                             "Bir nesneyi seçmek için üzerine tıklayın", self.delete_selected)
        btn.setEnabled(False)
        self._scene.selectionChanged.connect(lambda: self._sync_delete_button(btn))

    def _sync_delete_button(self, btn) -> None:
        try:
            btn.setEnabled(bool(self.selected_annotations()))
        except RuntimeError:
            pass  # pencere kapanırken sahne/düğme çoktan silinmiş olabilir

    # ---- koordinatlar ----
    def scene_pos(self, pos: QPointF) -> QPointF:
        return self.viewportTransform().inverted()[0].map(pos)

    def view_pos(self, scene_pt: QPointF) -> QPointF:
        return self.viewportTransform().map(scene_pt)

    # ---- araç / stil ----
    def _color_key(self, tool: str | None = None) -> str:
        return "highlighter" if (tool or self.tool) == "highlighter" else "default"

    def current_color(self) -> QColor:
        return QColor(self.colors[self._color_key()])

    def set_tool(self, tool: str) -> None:
        if tool not in TOOLS:
            return
        self.finish_text_editing()
        self.tool = tool
        self.toolChanged.emit(tool)
        self.viewport().update()

    def set_color(self, color: QColor) -> None:
        self.colors[self._color_key()] = QColor(color)
        self._apply_to_selected(lambda it: it.set_style(color=color), "Renk")
        self.styleChanged.emit()

    def set_text_style(self, style: str) -> None:
        self.text_style = style
        self._apply_to_selected(lambda it: it.set_style(style=style) if isinstance(it, TextItem) else None,
                                "Yazı stili")
        self.styleChanged.emit()

    def set_level(self, level: int) -> None:
        self.level = level
        self._apply_to_selected(lambda it: it.set_style(size=size_for(it.kind, level, self.ui_scale)), "Kalınlık")
        self.styleChanged.emit()

    # ---- nesneler ----
    def annotations(self) -> list:
        return sorted((it for it in self._scene.items() if is_annotation(it)), key=lambda it: it.zValue())

    def selected_annotations(self) -> list:
        return [it for it in self._scene.selectedItems() if is_annotation(it)]

    def delete_selected(self) -> bool:
        items = self.selected_annotations()
        if not items:
            return False
        self.finish_text_editing()
        self.undo_stack.push(RemoveItemsCommand(self._scene, items))
        return True

    def _apply_to_selected(self, fn, text: str) -> None:
        items = self.selected_annotations()
        if not items:
            return
        before = [it.state() for it in items]
        for it in items:
            fn(it)
        after = [it.state() for it in items]
        if before != after:
            self.undo_stack.push(StateCommand(items, before, after, text))

    def _add_new(self, item) -> None:
        self._z += 1
        item.setZValue(self._z)
        self._scene.addItem(item)

    def _next_step_number(self) -> int:
        nums = [it.number for it in self.annotations() if isinstance(it, StepItem)]
        return max(nums, default=0) + 1

    def _snapshot(self, items: list) -> list[tuple]:
        return [(it, it.state()) for it in items]

    def _push_changes(self, snapshot: list[tuple], text: str) -> None:
        items, before, after = [], [], []
        for it, old in snapshot:
            new = it.state()
            if new != old:
                items.append(it)
                before.append(old)
                after.append(new)
        if items:
            self.undo_stack.push(StateCommand(items, before, after, text))

    # ---- yazı ----
    def finish_text_editing(self) -> None:
        if self._editing_text is not None:
            item, self._editing_text = self._editing_text, None
            item.stop_editing()

    def _edit_text(self, item: TextItem) -> None:
        self.finish_text_editing()
        self._scene.clearSelection()
        item.setSelected(True)
        item.on_edit_finished = self._on_text_finished
        self._editing_text = item
        item.start_editing()

    def _on_text_finished(self, item: TextItem) -> None:
        if self._editing_text is item:
            self._editing_text = None
        was_new, item.is_new = item.is_new, False
        if item.is_degenerate():
            if was_new:
                if item.scene() is self._scene:
                    self._scene.removeItem(item)
            elif item.scene() is self._scene:
                self.undo_stack.push(RemoveItemsCommand(self._scene, [item]))
            return
        if was_new:
            self.undo_stack.push(AddItemsCommand(self._scene, [item], "Yazı"))
        elif item.edit_before is not None and item.edit_before != item.state():
            self.undo_stack.push(StateCommand([item], [item.edit_before], [item.state()], "Yazı"))

    # ---- fare yardımcıları (alt sınıf kendi olay işleyicisinden çağırır) ----
    def annotation_at(self, pos: QPointF):
        for it in self.items(pos.toPoint()):
            if is_annotation(it):
                return it
        return None

    def annotation_handle_at(self, pos: QPointF):
        for it in self.selected_annotations():
            for name, sp in it.handles().items():
                vp = self.view_pos(sp)
                if abs(vp.x() - pos.x()) <= ITEM_HANDLE_HIT and abs(vp.y() - pos.y()) <= ITEM_HANDLE_HIT:
                    return it, name
        return None

    def annotation_cursor(self, pos: QPointF):
        """İmlecin altına göre uygun fare imleci (ya da None)."""
        if self.annotation_handle_at(pos):
            return Qt.CursorShape.SizeAllCursor
        if self.tool == "select":
            return Qt.CursorShape.SizeAllCursor if self.annotation_at(pos) else None
        if self.edit_rect.isEmpty() or not QRectF(self.edit_rect).contains(self.scene_pos(pos)):
            return None
        if self.tool == "text":
            return Qt.CursorShape.IBeamCursor
        return Qt.CursorShape.CrossCursor

    def annotation_press(self, e) -> bool:
        """Sol tık. Olayı kullandıysa True döner."""
        pos = e.position()
        sp = self.scene_pos(pos)
        hit = self.annotation_handle_at(pos)
        if hit:
            self._handle_drag = hit
            self._press_snapshot = self._snapshot([hit[0]])
            return True

        if self.tool == "select":
            item = self.annotation_at(pos)
            if item is None:
                self.finish_text_editing()
                self._scene.clearSelection()
                return False
            if item is self._editing_text:
                QGraphicsView.mousePressEvent(self, e)   # yazının içinde imleç konumlandırma
                return True
            self.finish_text_editing()
            self._press_snapshot = self._snapshot(self.annotations())
            QGraphicsView.mousePressEvent(self, e)
            return True

        if self.edit_rect.isEmpty() or not QRectF(self.edit_rect).contains(sp):
            return False

        if self.tool == "text":
            item = self.annotation_at(pos)
            if isinstance(item, TextItem):
                if item is self._editing_text:
                    QGraphicsView.mousePressEvent(self, e)
                else:
                    self._edit_text(item)
                return True
            if self._editing_text is not None:
                self.finish_text_editing()        # ilk tık sadece yazmayı bitirir
                return True
            self._begin_draw(sp, e.modifiers())
            return True

        self.finish_text_editing()
        if self.tool == "step" and isinstance(self.annotation_at(pos), StepItem):
            self.select_only(self.annotation_at(pos))   # var olan adıma tıklamak onu seçer
            return True
        self._scene.clearSelection()
        self._draw_press_pos = QPointF(pos)
        self._begin_draw(sp, e.modifiers())
        return True

    def annotation_move(self, e) -> bool:
        constrain = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._handle_drag:
            item, name = self._handle_drag
            item.drag_handle(name, self.scene_pos(e.position()), constrain)
            return True
        if self._draw_item is not None:
            self._update_draw(self.scene_pos(e.position()), constrain)
            return True
        if self._press_snapshot is not None or (self._editing_text is not None and e.buttons()):
            QGraphicsView.mouseMoveEvent(self, e)
            return True
        return False

    def annotation_release(self, e) -> bool:
        if self._handle_drag:
            self._handle_drag = None
            self._push_changes(self._press_snapshot, "Boyutlandır")
            self._press_snapshot = None
            return True
        if self._draw_item is not None:
            d = e.position() - self._draw_press_pos
            self._end_draw(is_click=abs(d.x()) + abs(d.y()) < CLICK_DISTANCE)
            return True
        if self._press_snapshot is not None:
            QGraphicsView.mouseReleaseEvent(self, e)
            self._push_changes(self._press_snapshot, "Taşı")
            self._press_snapshot = None
            return True
        if self._editing_text is not None:
            QGraphicsView.mouseReleaseEvent(self, e)
            return True
        return False

    def annotation_double_click(self, e) -> bool:
        item = self.annotation_at(e.position())
        if isinstance(item, TextItem) and self.tool in ("select", "text"):
            if item is self._editing_text:
                QGraphicsView.mouseDoubleClickEvent(self, e)   # kelime seçimi
            else:
                self._edit_text(item)
            return True
        if self.tool != "select":
            return self.annotation_press(e)
        return item is not None

    def annotation_key(self, e) -> bool:
        """Klavye. Olayı kullandıysa True döner."""
        if self._editing_text is not None:
            if e.key() == Qt.Key.Key_Escape:
                self.finish_text_editing()
            else:
                QGraphicsView.keyPressEvent(self, e)   # tüm tuşlar yazıya
            return True
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        key = e.key()
        if ctrl and key == Qt.Key.Key_Z and not shift:
            self.undo_stack.undo()
            return True
        if ctrl and (key == Qt.Key.Key_Y or (key == Qt.Key.Key_Z and shift)):
            self.undo_stack.redo()
            return True
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            return self.delete_selected()
        if key in _ARROWS and self.selected_annotations():
            # Ok tuşları: seçili nesneyi 1 px (Shift: 10 px) kaydır
            dx, dy = _ARROWS[key]
            step = (10 if shift else 1) * self.ui_scale
            items = self.selected_annotations()
            snapshot = self._snapshot(items)
            for it in items:
                it.moveBy(dx * step, dy * step)
            self._push_changes(snapshot, "Kaydır")
            return True
        return False

    # ---- çizim ----
    def _begin_draw(self, sp: QPointF, modifiers) -> None:
        t = self.tool
        color = self.current_color()
        size = size_for(t, self.level, self.ui_scale)
        if t == "step":
            item = StepItem(color, size, self._next_step_number())
            item.setPos(sp)
            self._add_new(item)
            self.undo_stack.push(AddItemsCommand(self._scene, [item], "Adım"))
            self._scene.clearSelection()
            return
        if t == "text":
            item = TextItem(color, size, style=self.text_style)
            item.is_new = True
            item.setPos(sp - QPointF(4, size * 0.75))
            self._add_new(item)
            self._edit_text(item)
            return
        if t in ("line", "arrow"):
            item = (ArrowItem if t == "arrow" else LineItem)(color, size)
        elif t == "rect":
            item = RectItem(color, size)
        elif t == "ellipse":
            item = EllipseItem(color, size)
        elif t in ("blur", "pixelate"):
            item = CensorItem(t, self.base_image, size)
        else:  # pen, highlighter
            item = PenItem(t, color, size)
            item.add_point(QPointF(0, 0))
        item.setPos(sp)
        self._add_new(item)
        self._draw_item = item
        self._draw_origin = QPointF(sp)

    def _update_draw(self, sp: QPointF, constrain: bool) -> None:
        item = self._draw_item
        local = sp - self._draw_origin
        if isinstance(item, LineItem):
            item.set_points(p2=snap_45(local) if constrain else local)
        elif isinstance(item, RectItem):
            if constrain:
                side = max(abs(local.x()), abs(local.y()))
                local = QPointF(side if local.x() >= 0 else -side, side if local.y() >= 0 else -side)
            item.set_geom_rect(QRectF(QPointF(0, 0), local).normalized())
        elif isinstance(item, PenItem):
            item.add_point(local)

    def _end_draw(self, is_click: bool = False) -> None:
        item, self._draw_item = self._draw_item, None
        if is_click or item.is_degenerate():
            self._scene.removeItem(item)
            # Sürüklemeden bir nesneye tıklamak: o nesneyi seç (Delete ile silinebilsin)
            target = self.annotation_at(self._draw_press_pos) if is_click else None
            if target is not None:
                self.select_only(target)
                return
            if not (is_click and isinstance(item, PenItem)):
                return
            self._scene.addItem(item)   # boş yere kalemle tıklama: nokta koy
        self.undo_stack.push(AddItemsCommand(self._scene, [item]))
        # Yeni çizilen nesne seçili kalsın: hemen boyutlandırılabilir / rengi değiştirilebilir
        self.select_only(item)

    def select_only(self, item) -> None:
        self._scene.clearSelection()
        item.setSelected(True)
        self.viewport().update()

    def show_item_menu(self, pos: QPointF) -> bool:
        """Sağ tık: nesnenin üzerindeyse onu seçip menü göster. Gösterdiyse True."""
        item = self.annotation_at(pos)
        if item is None:
            return False
        if not item.isSelected():
            self.finish_text_editing()
            self.select_only(item)
        menu = QMenu(self)
        menu.setStyleSheet(BAR_QSS)
        count = len(self.selected_annotations())
        act = menu.addAction(icons.tool_icon("delete"), "Sil" + (f" ({count} nesne)" if count > 1 else "") + "\tDelete")
        act.triggered.connect(self.delete_selected)
        menu.exec(self.viewport().mapToGlobal(pos.toPoint()))
        self.viewport().update()
        return True

    def contextMenuEvent(self, e):
        if not self.show_item_menu(QPointF(e.pos())):
            e.ignore()

    # ---- JSON (geçmiş için) ----
    def load_annotations(self, states: list[dict]) -> None:
        for state in states:
            try:
                self._add_new(item_from_state(state, self.base_image))
            except (KeyError, ValueError, TypeError):
                continue  # bozuk bir kayıt diğerlerini engellemesin

    def annotation_states(self, offset: QPoint | None = None) -> list[dict]:
        """Çizimlerin durumları; offset verilirse konumlar ondan göreli yazılır."""
        self.finish_text_editing()
        dx, dy = (offset.x(), offset.y()) if offset is not None else (0, 0)
        out = []
        for it in self.annotations():
            if it.is_degenerate():
                continue
            state = it.state()
            state["pos"] = [round(state["pos"][0] - dx, 2), round(state["pos"][1] - dy, 2)]
            out.append(state)
        return out

    # ---- çıktı ----
    def render_image(self) -> QImage:
        """edit_rect alanını, çizimlerle birlikte tek bir görüntü olarak verir."""
        self.finish_text_editing()
        selected = self._scene.selectedItems()
        self._scene.clearSelection()
        r = QRect(self.edit_rect)
        img = QImage(r.size(), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.black)
        p = QPainter(img)
        p.drawImage(QPointF(0, 0), self.base_image, r)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._scene.render(p, QRectF(0, 0, r.width(), r.height()), QRectF(r))
        p.end()
        for it in selected:
            it.setSelected(True)
        out = img.convertToFormat(QImage.Format.Format_RGB32)
        out.setDevicePixelRatio(1.0)
        return out

    # ---- çizim katmanları ----
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor(45, 45, 48))
        painter.drawImage(QPointF(0, 0), self.base_image)

    def paint_annotation_overlay(self, p: QPainter) -> None:
        """Seçili nesnelerin çerçevesi ve tutamaçları (görünüm koordinatında çizilir)."""
        for it in self.selected_annotations():
            br = self.viewportTransform().mapRect(it.sceneBoundingRect())
            pen = QPen(QColor(255, 255, 255, 200), 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(br)
            p.setPen(QPen(ACCENT, 1.5))
            p.setBrush(QColor("white"))
            s = ITEM_HANDLE
            for sp in it.handles().values():
                vp = self.view_pos(sp)
                p.drawEllipse(QRectF(vp.x() - s / 2, vp.y() - s / 2, s, s))

    def drawForeground(self, painter, rect):
        painter.save()
        painter.resetTransform()
        self.paint_annotation_overlay(painter)
        painter.restore()

    # ---- varsayılan olay işleyicileri (bağımsız düzenleyici penceresi için) ----
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.annotation_press(e)
        self.viewport().update()

    def mouseMoveEvent(self, e):
        if not self.annotation_move(e):
            cursor = self.annotation_cursor(e.position())
            self.viewport().setCursor(cursor if cursor is not None else Qt.CursorShape.ArrowCursor)
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.annotation_release(e)
        self.viewport().update()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.annotation_double_click(e)
        self.viewport().update()

    def keyPressEvent(self, e):
        if not self.annotation_key(e):
            super().keyPressEvent(e)
        self.viewport().update()

    def wheelEvent(self, e):
        e.accept()  # kaydırmayı kapat
