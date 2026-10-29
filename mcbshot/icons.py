"""Kod ile çizilen simgeler (harici resim dosyasına gerek kalmasın diye).

Tüm araç simgeleri 24x24'lük bir ızgarada tasarlanır ve büyük boyutta çizilir.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_ICON_PX = 64


def _begin(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    return pm, p


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm, p = _begin(size)
        grad = QLinearGradient(0, 0, 24, 24)
        grad.setColorAt(0, QColor("#4da3ff"))
        grad.setColorAt(1, QColor("#1f5fd6"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(1, 1, 22, 22), 5, 5)
        pen = QPen(QColor("white"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        # vizör köşeleri
        for x, y, dx, dy in ((6, 6, 1, 1), (18, 6, -1, 1), (6, 18, 1, -1), (18, 18, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 4 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 4 * dy))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(12, 12), 2, 2)
        p.end()
        icon.addPixmap(pm)
    return icon


def color_icon(color: QColor) -> QIcon:
    pm, p = _begin(_ICON_PX)
    p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
    p.setBrush(QColor(color))
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 4, 4)
    p.end()
    return QIcon(pm)


def width_icon(width: float, color: str = "#f0f0f0") -> QIcon:
    pm, p = _begin(_ICON_PX)
    p.setPen(QPen(QColor(color), min(width * 0.8, 10), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(5, 12), QPointF(19, 12))
    p.end()
    return QIcon(pm)


def _undo_path(p: QPainter) -> None:
    path = QPainterPath()
    path.moveTo(9, 9)
    path.lineTo(15, 9)
    path.quadTo(20, 9, 20, 14)
    path.quadTo(20, 19, 15, 19)
    path.lineTo(9, 19)
    p.drawPath(path)
    p.drawPolyline(QPolygonF([QPointF(12.5, 5.5), QPointF(9, 9), QPointF(12.5, 12.5)]))


def tool_icon(name: str, color: str = "#f0f0f0") -> QIcon:
    pm, p = _begin(_ICON_PX)
    fg = QColor(color)
    pen = QPen(fg, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    if name == "copy":
        p.drawRoundedRect(QRectF(8, 8, 12, 12), 2, 2)
        path = QPainterPath()
        path.moveTo(16, 5)
        path.lineTo(6, 5)
        path.quadTo(4, 5, 4, 7)
        path.lineTo(4, 16)
        p.drawPath(path)
    elif name == "save":
        p.drawLine(QPointF(12, 3), QPointF(12, 15))
        p.drawPolyline(QPolygonF([QPointF(7, 10), QPointF(12, 15), QPointF(17, 10)]))
        p.drawPolyline(QPolygonF([QPointF(4, 15), QPointF(4, 20), QPointF(20, 20), QPointF(20, 15)]))
    elif name == "close":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "select":
        p.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(6, 19), QPointF(10, 15), QPointF(13, 21),
                                 QPointF(15.5, 20), QPointF(12.5, 14), QPointF(18, 14)]))
    elif name == "pen":
        path = QPainterPath()
        path.moveTo(4, 20)
        path.lineTo(5.5, 15)
        path.lineTo(16, 4.5)
        path.lineTo(19.5, 8)
        path.lineTo(9, 18.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawLine(QPointF(14, 6.5), QPointF(17.5, 10))
    elif name == "line":
        p.drawLine(QPointF(5, 19), QPointF(19, 5))
    elif name == "arrow":
        p.drawLine(QPointF(5, 19), QPointF(18, 6))
        p.drawPolyline(QPolygonF([QPointF(10, 6), QPointF(18, 6), QPointF(18, 14)]))
    elif name == "rect":
        p.drawRect(QRectF(4, 6, 16, 12))
    elif name == "ellipse":
        p.drawEllipse(QRectF(3, 6, 18, 12))
    elif name == "highlighter":
        hl = QColor("#ffd60a")
        hl.setAlpha(150)
        p.setPen(QPen(hl, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawLine(QPointF(3, 20), QPointF(21, 20))
        p.setPen(pen)
        p.drawPolygon(QPolygonF([QPointF(9, 3), QPointF(15, 3), QPointF(15, 11), QPointF(13.5, 15),
                                 QPointF(10.5, 15), QPointF(9, 11)]))
        p.drawLine(QPointF(9, 11), QPointF(15, 11))
    elif name == "text":
        p.drawLine(QPointF(5, 5), QPointF(19, 5))
        p.drawLine(QPointF(12, 5), QPointF(12, 20))
        p.drawLine(QPointF(9, 20), QPointF(15, 20))
    elif name == "step":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(11)
        p.setFont(font)
        p.drawText(QRectF(3, 3, 18, 18), Qt.AlignmentFlag.AlignCenter, "1")
    elif name == "blur":
        path = QPainterPath()
        path.moveTo(12, 3)
        path.quadTo(19, 11, 19, 15)
        path.cubicTo(19, 19, 15.5, 21, 12, 21)
        path.cubicTo(8.5, 21, 5, 19, 5, 15)
        path.quadTo(5, 11, 12, 3)
        p.drawPath(path)
    elif name == "pixelate":
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(4):
            for j in range(4):
                c = QColor(fg)
                c.setAlpha(230 if (i + j) % 2 == 0 else 90)
                p.setBrush(c)
                p.drawRect(QRectF(4 + i * 4, 4 + j * 4, 4, 4))
    elif name == "width":
        for y, w in ((7, 1), (12, 2.2), (17.5, 3.6)):
            p.setPen(QPen(fg, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(5, y), QPointF(19, y))
    elif name == "ocr":
        # tarama çerçevesi + yazı satırları
        for x, y, dx, dy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 4 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 4 * dy))
        p.drawLine(QPointF(7.5, 9), QPointF(16.5, 9))
        p.drawLine(QPointF(7.5, 12.5), QPointF(16.5, 12.5))
        p.drawLine(QPointF(7.5, 16), QPointF(13, 16))
    elif name == "textstyle":
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([QPointF(7.5, 16.5), QPointF(12, 7.5), QPointF(16.5, 16.5)]))
        p.drawLine(QPointF(9.3, 13), QPointF(14.7, 13))
    elif name == "crop":
        p.drawPolyline(QPolygonF([QPointF(7, 2.5), QPointF(7, 17), QPointF(21.5, 17)]))
        p.drawPolyline(QPolygonF([QPointF(2.5, 7), QPointF(17, 7), QPointF(17, 21.5)]))
    elif name == "zoom_in" or name == "zoom_out":
        p.drawEllipse(QPointF(10, 10), 6.5, 6.5)
        p.drawLine(QPointF(15, 15), QPointF(20.5, 20.5))
        p.drawLine(QPointF(7, 10), QPointF(13, 10))
        if name == "zoom_in":
            p.drawLine(QPointF(10, 7), QPointF(10, 13))
    elif name == "fit":
        for x, y, dx, dy in ((3, 3, 1, 1), (21, 3, -1, 1), (3, 21, 1, -1), (21, 21, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 5 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 5 * dy))
        p.drawRect(QRectF(8, 8, 8, 8))
    elif name == "scroll":
        p.drawRoundedRect(QRectF(5, 2.5, 14, 19), 2, 2)
        p.drawLine(QPointF(12, 6.5), QPointF(12, 15.5))
        p.drawPolyline(QPolygonF([QPointF(9, 12.5), QPointF(12, 15.5), QPointF(15, 12.5)]))
    elif name == "delete":
        p.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
        p.drawPolyline(QPolygonF([QPointF(9, 6.5), QPointF(9.5, 3.5), QPointF(14.5, 3.5), QPointF(15, 6.5)]))
        p.drawPolyline(QPolygonF([QPointF(6, 6.5), QPointF(7, 20.5), QPointF(17, 20.5), QPointF(18, 6.5)]))
        p.drawLine(QPointF(10, 10), QPointF(10, 17))
        p.drawLine(QPointF(14, 10), QPointF(14, 17))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(3, 19)
        path.lineTo(21, 19)
        path.lineTo(21, 9)
        path.lineTo(12, 9)
        path.lineTo(10, 6)
        path.lineTo(4, 6)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "undo":
        _undo_path(p)
    elif name == "redo":
        p.translate(24, 0)
        p.scale(-1, 1)
        _undo_path(p)
    p.end()
    return QIcon(pm)
