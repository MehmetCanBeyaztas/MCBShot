"""Uygulamanın giriş noktası: sistem tepsisi, global kısayol, yakalama oturumu."""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import traceback

from PySide6.QtCore import QDir, QLockFile, QObject, Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__, export, icons, ocr
from .capture import capture_all
from .editor.window import EditorWindow
from .gallery import GalleryWindow
from .history import HistoryStore
from .hotkey import HotkeyManager, describe_hotkey
from .overlay import CaptureSession
from .scroll import ScrollCaptureJob
from .settings import HOTKEYS, Settings, app_data_dir, autostart_command, get_autostart, set_autostart
from .settings_window import SettingsDialog

log = logging.getLogger(APP_NAME)

FALLBACK_HOTKEY = "Ctrl+Shift+X"


class MCBShotApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.settings = Settings()
        self.history = HistoryStore(parent=self)
        self.history.changed.connect(self._close_deleted_editors)
        self._gallery: GalleryWindow | None = None
        self._editors: dict[str, EditorWindow] = {}
        self._session: CaptureSession | None = None
        self._last_saved: str | None = None
        self.active_hotkey: str | None = None

        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self.start_capture)
        self._scroll_job = None
        self.active_hotkeys: dict[str, str] = {}

        # Menü kapanıp ekrandan silinsin diye yakalama biraz gecikmeli başlar
        self.menu = QMenu()
        self.act_capture = self.menu.addAction("Ekran görüntüsü al")
        self.act_capture.triggered.connect(lambda: QTimer.singleShot(250, self.start_capture))
        self.act_delayed = self.menu.addAction("Gecikmeli ekran görüntüsü")
        self.act_delayed.triggered.connect(self.start_delayed_capture)
        self.act_scroll = self.menu.addAction("Kaydırmalı (tüm sayfa) ekran görüntüsü")
        self.act_scroll.triggered.connect(lambda: QTimer.singleShot(250, self.start_scroll_capture))
        self.menu.addSeparator()
        self.act_history = self.menu.addAction("Geçmiş…")
        self.act_history.triggered.connect(self.show_gallery)
        act_folder = self.menu.addAction("Kayıt klasörünü aç")
        act_folder.triggered.connect(self.open_save_dir)
        act_settings = self.menu.addAction("Ayarlar…")
        act_settings.triggered.connect(self.show_settings)
        self.menu.addSeparator()
        act_quit = self.menu.addAction("Çıkış")
        act_quit.triggered.connect(self.quit)

        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.show()

        self.hotkeys = HotkeyManager()
        self.hotkeys.activated.connect(self._on_hotkey)
        self._register_hotkeys(announce=True)
        self._sync_autostart()
        QTimer.singleShot(3000, self._prune_history)

    # ---- kısayollar ----
    def _register_hotkeys(self, announce: bool = False) -> None:
        self.hotkeys.unregister_all()
        self.active_hotkeys = {}
        failed = []
        for name, (key, _label) in HOTKEYS.items():
            wanted = self.settings.get(key)
            if not wanted:
                continue
            ok, err = self.hotkeys.register(name, wanted)
            if ok:
                self.active_hotkeys[name] = wanted
            else:
                log.warning("Kısayol kaydedilemedi: %s (hata %s)", wanted, err)
                failed.append(wanted)

        # Ana kısayol alınamadıysa yedek kısayol
        capture_key = self.settings.get("hotkey_capture")
        if "capture" not in self.active_hotkeys and capture_key:
            ok, _ = self.hotkeys.register("capture", FALLBACK_HOTKEY)
            if ok:
                self.active_hotkeys["capture"] = FALLBACK_HOTKEY
        self._update_labels()

        if failed:
            msg = "Şu kısayollar başka bir program tarafından kullanılıyor: " + \
                  ", ".join(describe_hotkey(f) for f in failed) + "."
            if any("print" in f.lower() for f in failed):
                msg += " Windows'un 'Print Screen ile ekran yakalamayı aç' ayarını kapatın (README)."
            if self.active_hotkeys.get("capture") == FALLBACK_HOTKEY:
                msg += f" Ekran görüntüsü için şimdilik {FALLBACK_HOTKEY} kullanılıyor."
            msg += " Ayarlar'dan değiştirebilirsiniz."
            self.tray.showMessage(APP_NAME, msg, QSystemTrayIcon.MessageIcon.Warning, 10000)
        elif announce and "capture" in self.active_hotkeys:
            self.tray.showMessage(APP_NAME, f"MCBShot çalışıyor. {describe_hotkey(self.active_hotkeys['capture'])} "
                                  "tuşuyla ekran görüntüsü alın.", QSystemTrayIcon.MessageIcon.Information, 4000)

    def _update_labels(self) -> None:
        def label(text: str, name: str) -> str:
            hk = self.active_hotkeys.get(name)
            return f"{text}\t{describe_hotkey(hk)}" if hk else text
        delay = int(self.settings.get("delay_seconds"))
        self.act_capture.setText(label("Ekran görüntüsü al", "capture"))
        self.act_delayed.setText(label(f"Gecikmeli ekran görüntüsü ({delay} sn)", "delayed"))
        self.act_scroll.setText(label("Kaydırmalı (tüm sayfa) ekran görüntüsü", "scroll"))
        self.act_history.setText(label("Geçmiş…", "history"))
        hk = self.active_hotkeys.get("capture")
        self.tray.setToolTip(f"{APP_NAME} {__version__}" + (f" ({describe_hotkey(hk)})" if hk else ""))

    def _on_hotkey(self, name: str) -> None:
        if name == "capture":
            self.start_capture()
        elif name == "delayed":
            self.start_delayed_capture()
        elif name == "scroll":
            self.start_scroll_capture()
        elif name == "history":
            self.show_gallery()
        elif name == "scroll_stop" and self._scroll_job is not None:
            self._scroll_job.stop()

    # ---- ayarlar ----
    def show_settings(self) -> None:
        # Pencere açıkken kısayollar devre dışı: kutuya basılan tuş yakalamayı tetiklemesin
        self.hotkeys.unregister_all()

        def test_hotkey(text: str):
            ok, err = self.hotkeys.register("__test__", text)
            self.hotkeys.unregister("__test__")
            return ok, err

        dlg = SettingsDialog(self.settings, test_hotkey, history_count=self.history.count())
        dlg.exec()
        # Pencere hemen silinsin: aksi halde program kapanırken Qt'den sonra silinip çökmeye yol açar
        dlg.deleteLater()
        self._register_hotkeys()
        self._sync_autostart(from_settings=True)
        self._prune_history()

    def _sync_autostart(self, from_settings: bool = False) -> None:
        """Windows ile başlat.

        Açılışta (from_settings=False) asıl kaynak Windows kaydıdır: kurulum programı da bu kaydı
        yazabildiği için ayar ona göre güncellenir; program taşındıysa kayıttaki yol düzeltilir.
        Ayarlar penceresi kapanınca (from_settings=True) kullanıcının seçimi kayda yazılır.
        """
        try:
            current = get_autostart()
            if from_settings:
                if self.settings.get("start_with_windows"):
                    if current != autostart_command():
                        set_autostart(True)
                elif current is not None:
                    set_autostart(False)
                return
            enabled = current is not None
            # Kayıttaki program artık yoksa (taşındı/silindi) yolu bu kopyaya çevir
            registered = current.split('"')[1] if current and current.startswith('"') else current
            if enabled and registered and not os.path.exists(registered):
                set_autostart(True)
            if bool(self.settings.get("start_with_windows")) != enabled:
                self.settings.set("start_with_windows", enabled)
                self.settings.save()
        except OSError:
            log.exception("Windows ile başlat ayarı uygulanamadı")

    def _prune_history(self) -> None:
        try:
            removed = self.history.prune(int(self.settings.get("history_keep_days")),
                                         int(self.settings.get("history_max_items")), set(self._editors))
            if removed:
                log.info("Geçmiş temizliği: %d kayıt silindi", removed)
        except Exception:
            log.exception("Geçmiş temizlenemedi")

    # ---- yakalama ----
    def start_delayed_capture(self) -> None:
        if self._session is not None:
            return
        delay = max(1, int(self.settings.get("delay_seconds")))
        self.tray.setToolTip(f"{APP_NAME}: {delay} sn sonra ekran görüntüsü alınacak…")
        self._delay_timer.start(delay * 1000)

    def start_capture(self, scroll_mode: bool = False) -> None:
        if self._session is not None or self._scroll_job is not None:
            return
        self._update_labels()
        try:
            shots = capture_all(allow_span=bool(self.settings.get("span_monitors")))
        except Exception:
            log.exception("Ekran yakalanamadı")
            self.tray.showMessage(APP_NAME, "Ekran yakalanamadı. Ayrıntılar günlük dosyasında.",
                                  QSystemTrayIcon.MessageIcon.Critical, 6000)
            return
        if not shots:
            return
        self._session = CaptureSession(shots, self.settings, self.history, self, scroll_mode=scroll_mode)
        self._session.scrollRequested.connect(self._on_scroll_requested)
        self._session.saved.connect(self._on_saved)
        self._session.recorded.connect(self._index_text)
        self._session.recorded.connect(lambda *_: self._prune_history())
        self._session.ocrRequested.connect(self._run_ocr)
        self._session.finished.connect(self._on_session_finished)
        self._session.start()

    # ---- OCR ----
    def _index_text(self, entry_id: str, image) -> None:
        """Geçmişte görüntüdeki yazıyla arama yapılabilsin diye arka planda OCR."""
        def done(result, error):
            if result is not None and result.text.strip() and self.history.get(entry_id):
                self.history.set_ocr_text(entry_id, result.text)
        ocr.recognize_async(image, done)

    def _run_ocr(self, image, entry_id: str) -> None:
        def done(result, error):
            if error:
                self.tray.showMessage(APP_NAME, error, QSystemTrayIcon.MessageIcon.Warning, 8000)
                return
            text = result.text.strip()
            if not text:
                self.tray.showMessage(APP_NAME, "Seçili alanda yazı bulunamadı.",
                                      QSystemTrayIcon.MessageIcon.Information, 4000)
                return
            export.copy_text(text)
            if entry_id and self.history.get(entry_id):
                self.history.set_ocr_text(entry_id, text)
            preview = text if len(text) <= 120 else text[:117] + "…"
            msg = f"Metin panoya kopyalandı:\n{preview}"
            if result.fallback:
                msg += "\n\n" + ocr.FALLBACK_HINT
            self._last_saved = None
            self.tray.showMessage(APP_NAME, msg, QSystemTrayIcon.MessageIcon.Information, 6000)
        ocr.recognize_async(image, done)

    # ---- kaydırmalı yakalama ----
    def start_scroll_capture(self) -> None:
        self.start_capture(scroll_mode=True)

    def _on_scroll_requested(self, physical, logical, dpr: float) -> None:
        if self._scroll_job is not None:
            return
        self._scroll_dpr = dpr
        job = ScrollCaptureJob(physical, logical, self)
        job.finished.connect(self._on_scroll_finished)
        self._scroll_job = job
        # Esc: kaydırmayı bitir (iş sürerken geçici global kısayol)
        self.hotkeys.register("scroll_stop", "Esc")
        QTimer.singleShot(300, job.start)   # seçim katmanı ekrandan tamamen kalksın

    def _on_scroll_finished(self, image, reason: str) -> None:
        job, self._scroll_job = self._scroll_job, None
        self.hotkeys.unregister("scroll_stop")
        if job is not None:
            job.deleteLater()
        if image is None:
            return
        notes = {"limit": " En fazla uzunluğa ulaşıldığı için durduruldu.",
                 "nomatch": " Sayfanın bir kısmı eşleştirilemediği için orada durduruldu "
                            "(sayfada hareketli içerik olabilir)."}
        export.copy_image(image)
        try:
            entry_id = self.history.add(image, [], image, self._scroll_dpr)
        except Exception:
            log.exception("Kaydırmalı görüntü geçmişe eklenemedi")
            entry_id = ""
        self.tray.showMessage(APP_NAME, f"Uzun ekran görüntüsü hazır ({image.width()}×{image.height()}) ve panoya "
                              "kopyalandı. Düzenleyicide açıldı." + notes.get(reason, ""),
                              QSystemTrayIcon.MessageIcon.Information, 6000)
        if entry_id:
            self._index_text(entry_id, image)
            self.open_editor(entry_id)

    # ---- geçmiş ----
    def show_gallery(self) -> None:
        if self._gallery is None:
            self._gallery = GalleryWindow(self.history, self.settings)
            self._gallery.openRequested.connect(self.open_editor)
        self._gallery.refresh()
        self._gallery.show()
        self._gallery.raise_()
        self._gallery.activateWindow()

    def open_editor(self, entry_id: str) -> None:
        win = self._editors.get(entry_id)
        if win is None:
            entry = self.history.get(entry_id)
            if entry is None:
                return
            win = EditorWindow(self.history, entry, self.settings)
            win.closed.connect(lambda eid: self._editors.pop(eid, None))
            self._editors[entry_id] = win
        win.show()
        win.raise_()
        win.activateWindow()

    def _close_deleted_editors(self) -> None:
        for entry_id, win in list(self._editors.items()):
            if self.history.get(entry_id) is None:
                win.discard()

    def _on_session_finished(self) -> None:
        session, self._session = self._session, None
        if session is not None:
            session.deleteLater()

    def _on_saved(self, path: str) -> None:
        self._last_saved = path
        self.tray.showMessage(APP_NAME, f"Kaydedildi: {os.path.basename(path)}\nKlasörde göstermek için tıklayın.",
                              QSystemTrayIcon.MessageIcon.Information, 4000)

    def _on_message_clicked(self) -> None:
        if self._last_saved and os.path.exists(self._last_saved):
            subprocess.Popen(f'explorer /select,"{os.path.normpath(self._last_saved)}"')

    # ---- tepsi ----
    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # sol tık
            QTimer.singleShot(150, self.start_capture)

    def open_save_dir(self) -> None:
        folder = self.settings.get("save_dir")
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def quit(self) -> None:
        for win in list(self._editors.values()):
            win.close()   # açık düzenleyicilerdeki değişiklikler geçmişe yazılsın
        if self._gallery is not None:
            self._gallery.close()
            self._gallery.deleteLater()
            self._gallery = None
        if self._scroll_job is not None:
            self._scroll_job.stop(cancel=True)
        self.hotkeys.unregister_all()
        # Arka planda süren OCR işleri bitmeden süreç kapanırsa Windows uygulamayı çökertir
        QThreadPool.globalInstance().waitForDone(5000)
        self.history.close()
        self.tray.hide()
        self.app.quit()


def _setup_logging() -> str:
    path = str(app_data_dir() / "mcbshot.log")
    logging.basicConfig(
        filename=path, level=logging.INFO, encoding="utf-8",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return path


def main() -> int:
    if "--selftest" in sys.argv:
        from .selftest import run
        return run()
    log_path = _setup_logging()
    log.info("MCBShot %s başlıyor", __version__)

    def excepthook(exc_type, exc, tb):
        log.error("Beklenmeyen hata:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if QApplication.instance() is not None:
            QMessageBox.critical(None, APP_NAME, f"Beklenmeyen bir hata oluştu:\n{exc}\n\nAyrıntılar: {log_path}")

    sys.excepthook = excepthook

    try:
        # Bildirimlerde "python" yerine MCBShot görünsün
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MCBShot.App")
    except (AttributeError, OSError):
        pass

    # Kesirli ölçekleri (%125, %150) yuvarlamadan kullan -> koordinatlar kaymaz
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(icons.app_icon())

    lock = QLockFile(os.path.join(QDir.tempPath(), "MCBShot.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, APP_NAME, "MCBShot zaten çalışıyor.\n"
                                "Saatin yanındaki sistem tepsisinde simgesini bulabilirsiniz.")
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, "Sistem tepsisi bulunamadı.")
        return 1

    controller = MCBShotApp(app)  # noqa: F841 (uygulama boyunca yaşamalı)
    code = app.exec()
    lock.unlock()
    return code
