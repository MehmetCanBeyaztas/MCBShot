"""Ekran görüntüsü geçmişi (SQLite + dosyalar).

Her kayıt için:
  originals/<id>.png  -> çizimsiz ORİJİNAL görüntü (kayıpsız PNG)
  thumbs/<id>.png     -> galeri için küçük resim (çizimlerle birlikte)
  veritabanı satırı   -> tarih, boyut, çizimler (JSON), kaydedilen dosya yolu, OCR metni

Çizimler ayrı saklandığı için görüntü sonradan açılıp ok/yazı değiştirilebilir.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QImage

from . import APP_NAME

THUMB_SIZE = 320

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shots (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    scale       REAL NOT NULL DEFAULT 1.0,
    annotations TEXT NOT NULL DEFAULT '[]',
    saved_path  TEXT,
    ocr_text    TEXT
);
CREATE INDEX IF NOT EXISTS idx_shots_created ON shots(created_at);
"""


def history_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _norm(text: str) -> str:
    """Türkçe uyumlu, büyük/küçük harf duyarsız karşılaştırma için."""
    return text.replace("İ", "i").replace("I", "ı").lower().replace("ı", "i")


@dataclass
class Entry:
    id: str
    created_at: datetime
    updated_at: datetime
    width: int
    height: int
    scale: float
    annotations: list = field(default_factory=list)
    saved_path: str | None = None
    ocr_text: str | None = None
    crop: list[int] | None = None    # [x, y, genişlik, yükseklik]

    def display_date(self) -> str:
        return self.created_at.strftime("%d.%m.%Y %H:%M")

    def display_size(self) -> tuple[int, int]:
        return (self.crop[2], self.crop[3]) if self.crop else (self.width, self.height)

    def matches(self, query: str) -> bool:
        if not query:
            return True
        hay = _norm(" ".join([
            self.display_date(), self.created_at.strftime("%Y-%m-%d"),
            Path(self.saved_path).name if self.saved_path else "",
            self.ocr_text or "",
            " ".join(a.get("text", "") for a in self.annotations if a.get("type") == "text"),
        ]))
        return all(word in hay for word in _norm(query).split())


class HistoryStore(QObject):
    changed = Signal()   # bir kayıt eklendi / güncellendi / silindi

    def __init__(self, root: Path | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.root = Path(root) if root else history_dir()
        (self.root / "originals").mkdir(parents=True, exist_ok=True)
        (self.root / "thumbs").mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.root / "history.db"))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        # Eski veritabanlarına sonradan eklenen sütunlar
        columns = {r["name"] for r in self.db.execute("PRAGMA table_info(shots)")}
        if "crop" not in columns:
            self.db.execute("ALTER TABLE shots ADD COLUMN crop TEXT")
        self.db.commit()

    # ---- dosya yolları ----
    def original_path(self, entry_id: str) -> Path:
        return self.root / "originals" / f"{entry_id}.png"

    def thumb_path(self, entry_id: str) -> Path:
        return self.root / "thumbs" / f"{entry_id}.png"

    def original_image(self, entry_id: str) -> QImage:
        return QImage(str(self.original_path(entry_id)))

    def _write_thumb(self, entry_id: str, rendered: QImage) -> None:
        thumb = rendered.scaled(THUMB_SIZE, THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        thumb.save(str(self.thumb_path(entry_id)), "PNG")

    # ---- işlemler ----
    def add(self, original: QImage, annotations: list[dict], rendered: QImage, scale: float,
            saved_path: str | None = None) -> str:
        entry_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        if not original.save(str(self.original_path(entry_id)), "PNG"):
            raise OSError("Geçmiş görüntüsü kaydedilemedi")
        self._write_thumb(entry_id, rendered)
        now = datetime.now().isoformat(timespec="seconds")
        self.db.execute(
            "INSERT INTO shots (id, created_at, updated_at, width, height, scale, annotations, saved_path)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry_id, now, now, original.width(), original.height(), scale,
             json.dumps(annotations, ensure_ascii=False), saved_path))
        self.db.commit()
        self.changed.emit()
        return entry_id

    def update(self, entry_id: str, annotations: list[dict], rendered: QImage,
               crop: list[int] | None = None) -> None:
        """crop: [x, y, genişlik, yükseklik] ya da None (kırpılmamış)."""
        self._write_thumb(entry_id, rendered)
        self.db.execute("UPDATE shots SET annotations = ?, crop = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(annotations, ensure_ascii=False), json.dumps(crop) if crop else None,
                         datetime.now().isoformat(timespec="seconds"), entry_id))
        self.db.commit()
        self.changed.emit()

    def set_saved_path(self, entry_id: str, path: str) -> None:
        self.db.execute("UPDATE shots SET saved_path = ? WHERE id = ?", (path, entry_id))
        self.db.commit()
        self.changed.emit()

    def set_ocr_text(self, entry_id: str, text: str) -> None:
        self.db.execute("UPDATE shots SET ocr_text = ? WHERE id = ?", (text, entry_id))
        self.db.commit()   # arama için; galeriyi yeniden çizmeye gerek yok

    def delete(self, entry_id: str) -> None:
        self.db.execute("DELETE FROM shots WHERE id = ?", (entry_id,))
        self.db.commit()
        for path in (self.original_path(entry_id), self.thumb_path(entry_id)):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.changed.emit()

    def prune(self, keep_days: int = 0, max_items: int = 0, protect: set[str] | None = None) -> int:
        """Eski kayıtları siler (0 = sınır yok). protect: silinmeyecek kimlikler (açık düzenleyiciler)."""
        protect = protect or set()
        doomed: list[str] = []
        rows = self.db.execute("SELECT id, created_at FROM shots ORDER BY created_at DESC, id DESC").fetchall()
        if keep_days > 0:
            cutoff = datetime.now() - timedelta(days=keep_days)
            doomed += [r["id"] for r in rows if datetime.fromisoformat(r["created_at"]) < cutoff]
        if max_items > 0:
            doomed += [r["id"] for r in rows[max_items:]]
        doomed = [i for i in dict.fromkeys(doomed) if i not in protect]
        if not doomed:
            return 0
        self.db.executemany("DELETE FROM shots WHERE id = ?", [(i,) for i in doomed])
        self.db.commit()
        for entry_id in doomed:
            for path in (self.original_path(entry_id), self.thumb_path(entry_id)):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        self.changed.emit()
        return len(doomed)

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM shots").fetchone()[0]

    @staticmethod
    def _entry(row: sqlite3.Row) -> Entry:
        try:
            annotations = json.loads(row["annotations"])
        except ValueError:
            annotations = []
        try:
            crop = json.loads(row["crop"]) if row["crop"] else None
        except ValueError:
            crop = None
        return Entry(
            id=row["id"], created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]), width=row["width"], height=row["height"],
            scale=row["scale"], annotations=annotations, saved_path=row["saved_path"], ocr_text=row["ocr_text"],
            crop=crop)

    def get(self, entry_id: str) -> Entry | None:
        row = self.db.execute("SELECT * FROM shots WHERE id = ?", (entry_id,)).fetchone()
        return self._entry(row) if row else None

    def entries(self) -> list[Entry]:
        rows = self.db.execute("SELECT * FROM shots ORDER BY created_at DESC, id DESC").fetchall()
        return [self._entry(r) for r in rows]

    def close(self) -> None:
        self.db.close()
