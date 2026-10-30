"""Araç çubukları: dikey araç paneli (şekiller, renk, kalınlık) ve yatay işlem çubuğu."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QFrame, QGridLayout, QHBoxLayout, QMenu, QToolButton, QVBoxLayout,
                               QWidget, QWidgetAction)

from .. import icons
from ..i18n import N_, tr
from .items import TEXT_STYLES, WIDTH_NAMES, WIDTHS

TOOL_DEFS = (
    ("select", N_("Seç / taşı\nNesneleri seçip taşıyın; seçimin boş yerinden sürükleyerek alanı taşıyın")),
    ("pen", N_("Kalem")),
    ("line", N_("Çizgi (Shift: 45° açılar)")),
    ("arrow", N_("Ok (Shift: 45° açılar)")),
    ("rect", N_("Dikdörtgen (Shift: kare)")),
    ("ellipse", N_("Elips (Shift: daire)")),
    ("highlighter", N_("Vurgulayıcı")),
    ("text", N_("Yazı (çift tık: düzenle)")),
    ("step", N_("Numaralı adım (1, 2, 3...)")),
    ("blur", N_("Bulanıklaştır")),
    ("pixelate", N_("Pikselleştir")),
)

PALETTE = (
    "#ff3b30", "#ff9500", "#ffd60a", "#34c759", "#32ade6", "#007aff",
    "#af52de", "#ff2d55", "#ffffff", "#8e8e93", "#3a3a3c", "#000000",
)

BAR_QSS = """
QFrame#mcbBar {
    background: rgba(32, 33, 36, 240);
    border: 1px solid rgba(255, 255, 255, 45);
    border-radius: 6px;
}
QToolButton { border: none; border-radius: 4px; padding: 4px; }
QToolButton:hover { background: rgba(255, 255, 255, 35); }
QToolButton:pressed, QToolButton:checked { background: #2f8cff; }
QToolButton:disabled { background: transparent; }
QFrame#mcbSeparator { background: rgba(255, 255, 255, 50); }
QMenu { background: #2a2b2e; color: #eeeeee; border: 1px solid #555; padding: 4px; }
QMenu::item { padding: 5px 18px 5px 8px; border-radius: 3px; }
QMenu::item:selected { background: #2f8cff; }
QMenu::separator { height: 1px; background: #555; margin: 4px 2px; }
"""


class Bar(QFrame):
    def __init__(self, parent: QWidget, vertical: bool = False):
        super().__init__(parent)
        self.setObjectName("mcbBar")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(BAR_QSS)
        self._vertical = vertical
        self._layout = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)

    def add_button(self, icon, tooltip: str, slot=None, checkable: bool = False) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(icon)
        btn.setIconSize(QSize(20, 20))
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # klavye kısayolları tuvalde kalsın
        if slot is not None:
            btn.clicked.connect(lambda checked=False: slot())
        self._layout.addWidget(btn)
        return btn

    def add_separator(self) -> None:
        sep = QFrame(self)
        sep.setObjectName("mcbSeparator")
        sep.setFixedSize(*((20, 1) if self._vertical else (1, 20)))
        self._layout.addWidget(sep, 0, Qt.AlignmentFlag.AlignCenter)


class ToolPanel(Bar):
    """Şekil araçları + renk + kalınlık. Bir AnnotationView'e bağlanır."""

    def __init__(self, parent: QWidget, view):
        super().__init__(parent, vertical=True)
        self.view = view
        self._buttons: dict[str, QToolButton] = {}
        for name, tip in TOOL_DEFS:
            self._buttons[name] = self.add_button(icons.tool_icon(name), tr(tip),
                                                  lambda n=name: self._on_tool_clicked(n), checkable=True)
        self.add_separator()
        self.color_btn = self.add_button(icons.color_icon(view.current_color()), tr("Renk"), self._show_color_menu)
        self.width_btn = self.add_button(icons.tool_icon("width"), tr("Kalınlık / boyut"), self._show_width_menu)
        self.text_style_btn = self.add_button(icons.tool_icon("textstyle"), tr("Yazı arka planı (kutu / kontur)"),
                                              self._show_text_style_menu)
        view.toolChanged.connect(self._sync)
        view.styleChanged.connect(self._sync)
        self._sync()

    def _on_tool_clicked(self, name: str) -> None:
        # Seçili araca tekrar tıklamak araç seçimini kaldırır
        if name == self.view.tool and name != "select":
            name = "select"
        self.view.set_tool(name)
        self._sync()

    def _sync(self, *_):
        for name, btn in self._buttons.items():
            btn.setChecked(name == self.view.tool)
        self.color_btn.setIcon(icons.color_icon(self.view.current_color()))

    def _popup(self, menu: QMenu, btn: QToolButton) -> None:
        menu.exec(btn.mapToGlobal(QPoint(btn.width() + 6, 0)))

    def _show_color_menu(self) -> None:
        menu = QMenu(self)
        grid_host = QWidget(menu)
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(3)
        for i, hex_color in enumerate(PALETTE):
            b = QToolButton(grid_host)
            b.setIcon(icons.color_icon(QColor(hex_color)))
            b.setIconSize(QSize(22, 22))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setStyleSheet("QToolButton{border:none;padding:2px;border-radius:3px}"
                            "QToolButton:hover{background:rgba(255,255,255,40)}")
            b.clicked.connect(lambda checked=False, c=hex_color: self._choose_color(menu, QColor(c)))
            grid.addWidget(b, i // 6, i % 6)
        action = QWidgetAction(menu)
        action.setDefaultWidget(grid_host)
        menu.addAction(action)
        menu.addSeparator()
        other = menu.addAction(tr("Diğer renk…"))
        other.triggered.connect(self._pick_custom_color)
        self._popup(menu, self.color_btn)

    def _choose_color(self, menu: QMenu, color: QColor) -> None:
        menu.close()
        self.view.set_color(color)

    def _pick_custom_color(self) -> None:
        color = QColorDialog.getColor(self.view.current_color(), self.window(), tr("Renk seç"))
        if color.isValid():
            self.view.set_color(color)

    def _show_text_style_menu(self) -> None:
        menu = QMenu(self)
        for key, label in TEXT_STYLES.items():
            act = menu.addAction(tr(label))
            act.setCheckable(True)
            act.setChecked(key == self.view.text_style)
            act.triggered.connect(lambda checked=False, k=key: self.view.set_text_style(k))
        self._popup(menu, self.text_style_btn)

    def _show_width_menu(self) -> None:
        menu = QMenu(self)
        for level, (w, label) in enumerate(zip(WIDTHS, WIDTH_NAMES)):
            act = menu.addAction(icons.width_icon(w), tr(label))
            act.setCheckable(True)
            act.setChecked(level == self.view.level)
            act.triggered.connect(lambda checked=False, lv=level: self.view.set_level(lv))
        self._popup(menu, self.width_btn)
