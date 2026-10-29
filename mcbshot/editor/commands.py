"""Geri al / ileri al komutları (QUndoStack ile)."""
from __future__ import annotations

from PySide6.QtGui import QUndoCommand
from PySide6.QtWidgets import QGraphicsScene


class AddItemsCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, items: list, text: str = "Ekle"):
        super().__init__(text)
        self.scene = scene
        self.items = list(items)

    def redo(self):
        for item in self.items:
            if item.scene() is not self.scene:
                self.scene.addItem(item)

    def undo(self):
        for item in self.items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)


class RemoveItemsCommand(QUndoCommand):
    def __init__(self, scene: QGraphicsScene, items: list, text: str = "Sil"):
        super().__init__(text)
        self.scene = scene
        self.items = list(items)

    def redo(self):
        for item in self.items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)

    def undo(self):
        for item in self.items:
            if item.scene() is not self.scene:
                self.scene.addItem(item)


class CropCommand(QUndoCommand):
    """Kırpma alanını değiştir (orijinal görüntü korunur, sadece görünen alan değişir)."""

    def __init__(self, view, before, after, text: str = "Kırp"):
        super().__init__(text)
        self.view = view
        self.before = before
        self.after = after

    def redo(self):
        self.view.set_crop(self.after)

    def undo(self):
        self.view.set_crop(self.before)


class StateCommand(QUndoCommand):
    """Taşıma, boyutlandırma, renk/kalınlık, yazı değişikliği: önceki/sonraki durum."""

    def __init__(self, items: list, before: list[dict], after: list[dict], text: str = "Değiştir"):
        super().__init__(text)
        self.items = list(items)
        self.before = before
        self.after = after

    def redo(self):
        for item, state in zip(self.items, self.after):
            item.set_state(state)

    def undo(self):
        for item, state in zip(self.items, self.before):
            item.set_state(state)
