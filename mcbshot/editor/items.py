"""Düzenleyicideki çizim nesneleri.

Her şekil ayrı bir QGraphicsItem'dır: seçilebilir, taşınabilir, boyutlandırılabilir.
Sahne koordinatları = alttaki görüntünün fiziksel pikselleri.

Her nesne state() ile kendini sözlüğe (JSON'a uygun) çevirir, set_state() ile geri
yükler. Geri al/ileri al ve 3. aşamadaki "sonradan düzenleme" bunu kullanır.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF,
                           QTextCursor)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem, QStyle

from ..i18n import N_

WIDTHS = (2, 3, 5, 8, 12)      # kalınlık seviyeleri (mantıksal px)
WIDTH_NAMES = (N_("Çok ince"), N_("İnce"), N_("Orta"), N_("Kalın"), N_("Çok kalın"))
TEXT_STYLES = {"none": N_("Arka plan yok"), "box": N_("Kutu (arka plan)"), "glow": N_("Kontur")}
HIGHLIGHT_ALPHA = 110
MIN_HIT = 12.0                 # ince çizgileri de kolay yakalamak için


def size_for(kind: str, level: int, scale: float) -> float:
    """Kalınlık seviyesini nesne türüne göre sahne birimine çevirir."""
    level = max(0, min(level, len(WIDTHS) - 1))
    w = WIDTHS[level]
    if kind == "highlighter":
        return (w * 3 + 10) * scale
    if kind == "text":
        return (14 + level * 5) * scale          # yazı tipi boyutu
    if kind == "step":
        return (10 + level * 3) * scale          # daire yarıçapı
    if kind in ("blur", "pixelate"):
        return (5 + level * 3) * scale           # blok boyutu
    return w * scale


def rect_handle_points(r: QRectF) -> dict[str, QPointF]:
    cx, cy = r.center().x(), r.center().y()
    return {
        "tl": r.topLeft(), "t": QPointF(cx, r.top()), "tr": r.topRight(),
        "r": QPointF(r.right(), cy), "br": r.bottomRight(), "b": QPointF(cx, r.bottom()),
        "bl": r.bottomLeft(), "l": QPointF(r.left(), cy),
    }


def resize_rect(r: QRectF, name: str, pt: QPointF) -> QRectF:
    left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
    if "l" in name:
        left = pt.x()
    if "r" in name:
        right = pt.x()
    if "t" in name:
        top = pt.y()
    if "b" in name:
        bottom = pt.y()
    return QRectF(QPointF(left, top), QPointF(right, bottom)).normalized()


def snap_45(v: QPointF) -> QPointF:
    """Vektörü en yakın 45° açıya yaslar (Shift ile çizimde)."""
    length = math.hypot(v.x(), v.y())
    if length == 0:
        return v
    step = math.pi / 4
    ang = round(math.atan2(v.y(), v.x()) / step) * step
    return QPointF(math.cos(ang) * length, math.sin(ang) * length)


def contrast_color(c: QColor) -> QColor:
    lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return QColor("black") if lum > 170 else QColor("white")


def censor_image(img: QImage, kind: str, block: float) -> QImage:
    """Bulanıklaştır / pikselleştir: küçültüp yeniden büyütme."""
    b = max(2, int(round(block)))
    w, h = img.width(), img.height()
    small = img.scaled(max(1, round(w / b)), max(1, round(h / b)),
                       Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    mode = Qt.TransformationMode.FastTransformation if kind == "pixelate" else Qt.TransformationMode.SmoothTransformation
    return small.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, mode)


def _pt(p: QPointF) -> list[float]:
    return [round(p.x(), 2), round(p.y(), 2)]


def _color(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexArgb)


class ShapeItem(QGraphicsItem):
    """Kendi çizdiğimiz şekillerin ortak tabanı."""

    kind = "shape"

    def __init__(self, color: QColor, size: float):
        super().__init__()
        self.color = QColor(color)
        self.size = float(size)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def pen(self, color: QColor | None = None, join=Qt.PenJoinStyle.RoundJoin) -> QPen:
        return QPen(color or self.color, self.size, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, join)

    # ---- geometri ----
    def geom_rect(self) -> QRectF:
        raise NotImplementedError

    def set_geom_rect(self, r: QRectF) -> None:
        raise NotImplementedError

    def handles(self) -> dict[str, QPointF]:
        """Boyutlandırma tutamaçları (sahne koordinatında)."""
        return {k: self.mapToScene(v) for k, v in rect_handle_points(self.geom_rect()).items()}

    def drag_handle(self, name: str, scene_pt: QPointF, constrain: bool = False) -> None:
        self.set_geom_rect(resize_rect(self.geom_rect(), name, self.mapFromScene(scene_pt)))

    def is_degenerate(self) -> bool:
        return False

    def set_style(self, color: QColor | None = None, size: float | None = None) -> None:
        self.prepareGeometryChange()
        if color is not None:
            self.color = QColor(color)
        if size is not None:
            self.size = float(size)
        self.update()

    # ---- kaydetme / geri yükleme ----
    def state(self) -> dict:
        d = {"type": self.kind, "pos": _pt(self.pos()), "color": _color(self.color), "size": round(self.size, 2)}
        d.update(self.geom_state())
        return d

    def set_state(self, d: dict) -> None:
        self.prepareGeometryChange()
        self.setPos(QPointF(*d["pos"]))
        self.color = QColor(d["color"])
        self.size = float(d["size"])
        self.load_geom_state(d)
        self.update()

    def geom_state(self) -> dict:
        return {}

    def load_geom_state(self, d: dict) -> None:
        pass


class RectItem(ShapeItem):
    kind = "rect"

    def __init__(self, color: QColor, size: float, rect: QRectF | None = None):
        super().__init__(color, size)
        self.rect = QRectF(rect) if rect is not None else QRectF()

    def geom_rect(self) -> QRectF:
        return QRectF(self.rect)

    def set_geom_rect(self, r: QRectF) -> None:
        self.prepareGeometryChange()
        self.rect = QRectF(r).normalized()
        self.update()

    def boundingRect(self) -> QRectF:
        m = self.size / 2 + 2
        return self.rect.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen(join=Qt.PenJoinStyle.MiterJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect)

    def is_degenerate(self) -> bool:
        return self.rect.width() < 3 or self.rect.height() < 3

    def geom_state(self) -> dict:
        r = self.rect
        return {"rect": [round(r.x(), 2), round(r.y(), 2), round(r.width(), 2), round(r.height(), 2)]}

    def load_geom_state(self, d: dict) -> None:
        self.rect = QRectF(*d["rect"])


class EllipseItem(RectItem):
    kind = "ellipse"

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(self.rect)


class CensorItem(RectItem):
    """Bulanıklaştırma (blur) veya pikselleştirme (pixelate) alanı.

    Altındaki ORİJİNAL görüntüyü işler; size = blok boyutu.
    """

    def __init__(self, kind: str, source: QImage, size: float, rect: QRectF | None = None):
        super().__init__(QColor("black"), size, rect)
        self.kind = kind
        self.source = source
        self._cache_key = None
        self._cache: QImage | None = None

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-1, -1, 1, 1)

    def _processed(self, sr: QRect) -> QImage:
        key = (sr.x(), sr.y(), sr.width(), sr.height(), self.kind, round(self.size, 1))
        if key != self._cache_key:
            self._cache = censor_image(self.source.copy(sr), self.kind, self.size)
            self._cache_key = key
        return self._cache

    def paint(self, painter, option, widget=None):
        sr = self.mapRectToScene(self.rect).toAlignedRect().intersected(self.source.rect())
        if sr.width() < 1 or sr.height() < 1:
            return
        painter.drawImage(self.mapRectFromScene(QRectF(sr)), self._processed(sr))


class LineItem(ShapeItem):
    kind = "line"

    def __init__(self, color: QColor, size: float, p1: QPointF | None = None, p2: QPointF | None = None):
        super().__init__(color, size)
        self.p1 = QPointF(p1) if p1 is not None else QPointF()
        self.p2 = QPointF(p2) if p2 is not None else QPointF()

    def set_points(self, p1: QPointF | None = None, p2: QPointF | None = None) -> None:
        self.prepareGeometryChange()
        if p1 is not None:
            self.p1 = QPointF(p1)
        if p2 is not None:
            self.p2 = QPointF(p2)
        self.update()

    def geom_rect(self) -> QRectF:
        return QRectF(self.p1, self.p2).normalized()

    def set_geom_rect(self, r: QRectF) -> None:
        pass  # çizgiler uç noktalarından boyutlandırılır

    def handles(self) -> dict[str, QPointF]:
        return {"p1": self.mapToScene(self.p1), "p2": self.mapToScene(self.p2)}

    def drag_handle(self, name: str, scene_pt: QPointF, constrain: bool = False) -> None:
        local = self.mapFromScene(scene_pt)
        other = self.p2 if name == "p1" else self.p1
        if constrain:
            local = other + snap_45(local - other)
        self.set_points(**{name: local})

    def boundingRect(self) -> QRectF:
        m = self.size * 4 + 10
        return self.geom_rect().adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = QPainterPath(self.p1)
        path.lineTo(self.p2)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.size + 4, MIN_HIT))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(path)

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen())
        painter.drawLine(QLineF(self.p1, self.p2))

    def is_degenerate(self) -> bool:
        return QLineF(self.p1, self.p2).length() < 3

    def geom_state(self) -> dict:
        return {"p1": _pt(self.p1), "p2": _pt(self.p2)}

    def load_geom_state(self, d: dict) -> None:
        self.p1 = QPointF(*d["p1"])
        self.p2 = QPointF(*d["p2"])


class ArrowItem(LineItem):
    kind = "arrow"

    def paint(self, painter, option, widget=None):
        length = QLineF(self.p1, self.p2).length()
        if length < 0.5:
            return
        ux = (self.p2.x() - self.p1.x()) / length
        uy = (self.p2.y() - self.p1.y()) / length
        head = min(self.size * 3 + 8, length)
        half = head * 0.55
        base = QPointF(self.p2.x() - ux * head, self.p2.y() - uy * head)
        left = QPointF(base.x() - uy * half, base.y() + ux * half)
        right = QPointF(base.x() + uy * half, base.y() - ux * half)
        shaft_end = QPointF(base.x() + ux * head * 0.3, base.y() + uy * head * 0.3)

        painter.setPen(self.pen())
        painter.drawLine(QLineF(self.p1, shaft_end))
        painter.setPen(QPen(self.color, 1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(self.color)
        painter.drawPolygon(QPolygonF([self.p2, left, right]))


class PenItem(ShapeItem):
    """Serbest kalem (pen) ve vurgulayıcı (highlighter)."""

    def __init__(self, kind: str, color: QColor, size: float, points: list[QPointF] | None = None):
        super().__init__(color, size)
        self.kind = kind
        self.points = [QPointF(p) for p in (points or [])]
        self._path: QPainterPath | None = None

    def add_point(self, pt: QPointF) -> None:
        if self.points and QLineF(self.points[-1], pt).length() < 1:
            return
        self.prepareGeometryChange()
        self.points.append(QPointF(pt))
        self._path = None
        self.update()

    def path(self) -> QPainterPath:
        if self._path is None:
            path = QPainterPath()
            pts = self.points
            if pts:
                path.moveTo(pts[0])
                if len(pts) == 1:
                    path.lineTo(pts[0] + QPointF(0.01, 0))
                for i in range(1, len(pts)):
                    mid = (pts[i - 1] + pts[i]) * 0.5
                    path.quadTo(pts[i - 1], mid)
                if len(pts) > 1:
                    path.lineTo(pts[-1])
            self._path = path
        return self._path

    def draw_color(self) -> QColor:
        c = QColor(self.color)
        if self.kind == "highlighter":
            c.setAlpha(HIGHLIGHT_ALPHA)
        return c

    def boundingRect(self) -> QRectF:
        m = self.size / 2 + 2
        return self.path().boundingRect().adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.size, MIN_HIT))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen(self.draw_color()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

    def geom_rect(self) -> QRectF:
        return QPolygonF(self.points).boundingRect()

    def set_geom_rect(self, r: QRectF) -> None:
        old = self.geom_rect()
        sx = r.width() / old.width() if old.width() > 0.5 else 1.0
        sy = r.height() / old.height() if old.height() > 0.5 else 1.0
        self.prepareGeometryChange()
        self.points = [QPointF(r.x() + (p.x() - old.x()) * sx, r.y() + (p.y() - old.y()) * sy) for p in self.points]
        self._path = None
        self.update()

    def is_degenerate(self) -> bool:
        return not self.points

    def geom_state(self) -> dict:
        return {"points": [_pt(p) for p in self.points]}

    def load_geom_state(self, d: dict) -> None:
        self.points = [QPointF(x, y) for x, y in d["points"]]
        self._path = None


class StepItem(ShapeItem):
    """Numaralı adım işareti. size = daire yarıçapı, merkez = nesnenin konumu."""

    kind = "step"

    def __init__(self, color: QColor, size: float, number: int = 1):
        super().__init__(color, size)
        self.number = int(number)

    def geom_rect(self) -> QRectF:
        r = self.size
        return QRectF(-r, -r, 2 * r, 2 * r)

    def set_geom_rect(self, r: QRectF) -> None:
        pass

    def drag_handle(self, name: str, scene_pt: QPointF, constrain: bool = False) -> None:
        local = self.mapFromScene(scene_pt)
        self.set_style(size=max(4.0, abs(local.x()), abs(local.y())))

    def boundingRect(self) -> QRectF:
        r = self.size + 2
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        r = self.size
        painter.setPen(QPen(QColor("white"), max(1.0, r * 0.12)))
        painter.setBrush(self.color)
        painter.drawEllipse(QPointF(0, 0), r, r)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(4, int(r * (1.1 if self.number < 10 else 0.85))))
        painter.setFont(font)
        painter.setPen(contrast_color(self.color))
        painter.drawText(QRectF(-r, -r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(self.number))

    def geom_state(self) -> dict:
        return {"number": self.number}

    def load_geom_state(self, d: dict) -> None:
        self.number = int(d["number"])


class TextItem(QGraphicsTextItem):
    """Yazı. Çift tıkla düzenlenir. size = yazı tipi boyutu (px)."""

    kind = "text"

    def __init__(self, color: QColor, size: float, text: str = "", style: str = "none"):
        super().__init__()
        self.color = QColor(color)
        self.size = float(size)
        self.style = style if style in TEXT_STYLES else "none"   # arka plan: none | box | glow
        self.setPlainText(text)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.on_edit_finished = None   # düzenleme bitince çağrılır: fn(item)
        self.is_new = False
        self.edit_before: dict | None = None
        self._editing = False
        self._apply_style()

    def _apply_style(self) -> None:
        font = QFont("Segoe UI")
        font.setPixelSize(max(4, round(self.size)))
        font.setBold(True)
        self.setFont(font)
        self.setDefaultTextColor(self.color)
        self.update()

    def _outline_path(self) -> QPainterPath:
        """Belgedeki her satırın harf şekilleri (kontur çizmek için)."""
        path = QPainterPath()
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            layout = block.layout()
            origin = layout.position()
            for i in range(layout.lineCount()):
                line = layout.lineAt(i)
                text = block.text()[line.textStart():line.textStart() + line.textLength()]
                path.addText(QPointF(origin.x() + line.x(), origin.y() + line.y() + line.ascent()), self.font(), text)
            block = block.next()
        return path

    def set_style(self, color: QColor | None = None, size: float | None = None, style: str | None = None) -> None:
        if color is not None:
            self.color = QColor(color)
        if size is not None:
            self.size = float(size)
        if style in TEXT_STYLES:
            self.style = style
        self._apply_style()

    def handles(self) -> dict[str, QPointF]:
        return {}

    def drag_handle(self, name: str, scene_pt: QPointF, constrain: bool = False) -> None:
        pass

    def is_degenerate(self) -> bool:
        return not self.toPlainText().strip()

    def is_editing(self) -> bool:
        return self._editing

    def start_editing(self) -> None:
        self.edit_before = self.state()
        self._editing = True
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)

    def stop_editing(self) -> None:
        if not self._editing:
            return
        # Bayrak önce kapanmalı: etkileşimi kapatmak odağı düşürür ve bu fonksiyon tekrar çağrılır
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)
        self.clearFocus()
        if self.on_edit_finished is not None:
            # Sahneden silme gibi işler odak olayının içinde yapılmasın
            QTimer.singleShot(0, lambda: self.on_edit_finished(self))

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Renk menüsü / renk penceresi açılınca yazmaya devam edilebilsin
        if event.reason() not in (Qt.FocusReason.PopupFocusReason, Qt.FocusReason.ActiveWindowFocusReason):
            self.stop_editing()

    def paint(self, painter, option, widget=None):
        # Seçim çerçevesini görünüm kendisi çiziyor; Qt'nin kesikli çerçevesini kapat
        option.state = option.state & ~QStyle.StateFlag.State_Selected
        if self.style == "box":
            bg = contrast_color(self.color)
            bg.setAlpha(215)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg)
            radius = self.size * 0.25
            painter.drawRoundedRect(self.boundingRect().adjusted(1, 1, -1, -1), radius, radius)
            painter.restore()
        elif self.style == "glow":
            # Harflerin çevresine zıt renkte kontur: kalabalık arka planda okunur
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.strokePath(self._outline_path(), QPen(contrast_color(self.color), max(2.0, self.size * 0.2),
                                                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                                          Qt.PenJoinStyle.RoundJoin))
            painter.restore()
        super().paint(painter, option, widget)

    def state(self) -> dict:
        return {"type": "text", "pos": _pt(self.pos()), "color": _color(self.color),
                "size": round(self.size, 2), "text": self.toPlainText(), "style": self.style}

    def set_state(self, d: dict) -> None:
        self.setPos(QPointF(*d["pos"]))
        self.color = QColor(d["color"])
        self.size = float(d["size"])
        self.style = d.get("style", "none") if d.get("style") in TEXT_STYLES else "none"
        if self.toPlainText() != d["text"]:
            self.setPlainText(d["text"])
        self._apply_style()


def item_from_state(d: dict, source: QImage):
    """state() çıktısından yeni bir nesne oluşturur (3. aşamada JSON'dan yükleme için)."""
    kind = d["type"]
    color = QColor(d.get("color", "#ffff0000"))
    size = float(d.get("size", 3))
    if kind == "rect":
        item = RectItem(color, size)
    elif kind == "ellipse":
        item = EllipseItem(color, size)
    elif kind in ("blur", "pixelate"):
        item = CensorItem(kind, source, size)
    elif kind == "line":
        item = LineItem(color, size)
    elif kind == "arrow":
        item = ArrowItem(color, size)
    elif kind in ("pen", "highlighter"):
        item = PenItem(kind, color, size)
    elif kind == "step":
        item = StepItem(color, size)
    elif kind == "text":
        item = TextItem(color, size)
    else:
        raise ValueError(f"Bilinmeyen nesne türü: {kind}")
    item.set_state(d)
    return item


def is_annotation(item) -> bool:
    return isinstance(item, (ShapeItem, TextItem))
