"""Uygulamanın giriş noktası: sistem tepsisi, global kısayol, yakalama oturumu."""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import (QDir, QLibraryInfo, QLockFile, QObject, QProcess, Qt, QThreadPool, QTimer,
                            QTranslator, QUrl)
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, __version__, export, i18n, icons, ocr, updater
from .capture import capture_all
from .editor.window import EditorWindow
from .gallery import GalleryWindow
from .history import HistoryStore
from .hotkey import HotkeyManager, describe_hotkey
from .i18n import tr
from .overlay import CaptureSession
from .scroll import ScrollCaptureJob
from .settings import HOTKEYS, Settings, app_data_dir, autostart_command, get_autostart, set_autostart
from .settings_window import SettingsDialog

log = logging.getLogger(APP_NAME)

FALLBACK_HOTKEY = "Ctrl+Shift+X"
UPDATE_FIRST_CHECK_MS = 20_000
UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1000
UPDATE_RETRY_MS = 10 * 60 * 1000   # otomatik yükleme ertelendiyse tekrar dene


class MCBShotApp(QObject):
    def __init__(self, app: QApplication, settings: Settings | None = None):
        super().__init__()
        self.app = app
        self.settings = settings or Settings()
        self.history = HistoryStore(parent=self)
        self.history.changed.connect(self._close_deleted_editors)
        self._gallery: GalleryWindow | None = None
        self._editors: dict[str, EditorWindow] = {}
        self._session: CaptureSession | None = None
        self._message_action = None     # tepsi bildirimine tıklanınca yapılacak iş
        self.active_hotkey: str | None = None

        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self.start_capture)
        self._scroll_job = None
        self.active_hotkeys: dict[str, str] = {}

        # Güncelleme durumu
        self._update_busy = False
        self._update_release: updater.Release | None = None
        self._update_file: Path | None = None
        self._update_asked = False

        # Menü kapanıp ekrandan silinsin diye yakalama biraz gecikmeli başlar
        self.menu = QMenu()
        self.act_capture = self.menu.addAction(tr("Ekran görüntüsü al"))
        self.act_capture.triggered.connect(lambda: QTimer.singleShot(250, self.start_capture))
        self.act_delayed = self.menu.addAction(tr("Gecikmeli ekran görüntüsü"))
        self.act_delayed.triggered.connect(self.start_delayed_capture)
        self.act_scroll = self.menu.addAction(tr("Kaydırmalı (tüm sayfa) ekran görüntüsü"))
        self.act_scroll.triggered.connect(lambda: QTimer.singleShot(250, self.start_scroll_capture))
        self.menu.addSeparator()
        self.act_history = self.menu.addAction(tr("Geçmiş…"))
        self.act_history.triggered.connect(self.show_gallery)
        act_folder = self.menu.addAction(tr("Kayıt klasörünü aç"))
        act_folder.triggered.connect(self.open_save_dir)
        act_settings = self.menu.addAction(tr("Ayarlar…"))
        act_settings.triggered.connect(self.show_settings)
        self.act_check_update = self.menu.addAction(tr("Güncellemeleri denetle"))
        self.act_check_update.triggered.connect(lambda: self.check_updates(manual=True))
        self.act_install_update = self.menu.addAction("")
        self.act_install_update.triggered.connect(self.install_update)
        self.act_install_update.setVisible(False)
        self.menu.addSeparator()
        act_quit = self.menu.addAction(tr("Çıkış"))
        act_quit.triggered.connect(self.quit)

        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.show()

        self.hotkeys = HotkeyManager()
        self.hotkeys.activated.connect(self._on_hotkey)
        updated = self._note_version()
        self._register_hotkeys(announce=not updated)
        self._sync_autostart()
        QTimer.singleShot(3000, self._prune_history)

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(lambda: self.check_updates(manual=False))
        self._update_timer.start(UPDATE_INTERVAL_MS)
        QTimer.singleShot(UPDATE_FIRST_CHECK_MS, lambda: self.check_updates(manual=False))

    # ---- bildirimler ----
    def notify(self, text: str, icon=QSystemTrayIcon.MessageIcon.Information, ms: int = 4000, on_click=None) -> None:
        self._message_action = on_click
        self.tray.showMessage(APP_NAME, text, icon, ms)

    def _on_message_clicked(self) -> None:
        action, self._message_action = self._message_action, None
        if action is not None:
            action()

    def _note_version(self) -> bool:
        """Program güncellendiyse bir kez bildir. Güncellendiyse True."""
        last = self.settings.get("last_version")
        if last == __version__:
            return False
        self.settings.set("last_version", __version__)
        try:
            self.settings.save()
        except OSError:
            pass
        if last and updater.is_newer(__version__, last):
            self.notify(tr("MCBShot {version} sürümüne güncellendi.", version=__version__), ms=6000,
                        on_click=lambda: QDesktopServices.openUrl(QUrl(updater.RELEASES_URL)))
            return True
        return False

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
            msg = tr("Şu kısayollar başka bir program tarafından kullanılıyor: {keys}.",
                     keys=", ".join(describe_hotkey(f) for f in failed))
            if any("print" in f.lower() for f in failed):
                msg += tr(" Windows'un 'Print Screen ile ekran yakalamayı aç' ayarını kapatın (README).")
            if self.active_hotkeys.get("capture") == FALLBACK_HOTKEY:
                msg += tr(" Ekran görüntüsü için şimdilik {key} kullanılıyor.", key=FALLBACK_HOTKEY)
            msg += tr(" Ayarlar'dan değiştirebilirsiniz.")
            self.notify(msg, QSystemTrayIcon.MessageIcon.Warning, 10000)
        elif announce and "capture" in self.active_hotkeys:
            self.notify(tr("MCBShot çalışıyor. {key} tuşuyla ekran görüntüsü alın.",
                           key=describe_hotkey(self.active_hotkeys["capture"])))

    def _update_labels(self) -> None:
        def label(text: str, name: str) -> str:
            hk = self.active_hotkeys.get(name)
            return f"{text}\t{describe_hotkey(hk)}" if hk else text
        delay = int(self.settings.get("delay_seconds"))
        self.act_capture.setText(label(tr("Ekran görüntüsü al"), "capture"))
        self.act_delayed.setText(label(tr("Gecikmeli ekran görüntüsü ({delay} sn)", delay=delay), "delayed"))
        self.act_scroll.setText(label(tr("Kaydırmalı (tüm sayfa) ekran görüntüsü"), "scroll"))
        self.act_history.setText(label(tr("Geçmiş…"), "history"))
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

        old_language = self.settings.get("language")
        old_update_mode = self.settings.get("update_mode")
        dlg = SettingsDialog(self.settings, test_hotkey, history_count=self.history.count())
        accepted = dlg.exec()
        # Pencere hemen silinsin: aksi halde program kapanırken Qt'den sonra silinip çökmeye yol açar
        dlg.deleteLater()
        self._register_hotkeys()
        self._sync_autostart(from_settings=True)
        self._prune_history()
        if not accepted:
            return
        if self.settings.get("update_mode") != old_update_mode and self.settings.get("update_mode") != "off":
            QTimer.singleShot(1000, lambda: self.check_updates(manual=False))
        new_language = self.settings.get("language")
        if new_language != old_language:
            # Soru yeni dilde sorulsun; bundan sonra açılan pencereler de yeni dilde olur
            i18n.set_language(new_language)
            answer = QMessageBox.question(None, APP_NAME, tr("Dil değişikliği MCBShot yeniden başlatılınca "
                                                              "uygulanır. Şimdi yeniden başlatılsın mı?"))
            if answer == QMessageBox.StandardButton.Yes:
                self.restart()

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

    # ---- güncelleme ----
    def check_updates(self, manual: bool = False) -> None:
        if not manual and self.settings.get("update_mode") == "off":
            return
        if self._update_busy:
            return
        if self._update_file is not None:
            # Zaten indirildi: sadece yüklemeyi teklif et
            if manual:
                self._offer_update()
            return
        self._update_busy = True
        updater.run_async(updater.fetch_latest, lambda rel, err: self._on_update_checked(rel, err, manual))

    def _on_update_checked(self, release, error, manual: bool) -> None:
        self._update_busy = False
        if error:
            if manual:
                self.notify(tr("Güncelleme denetlenemedi: {error}", error=error),
                            QSystemTrayIcon.MessageIcon.Warning, 6000)
            return
        if release is None or not updater.is_newer(release.version):
            if manual:
                self.notify(tr("MCBShot güncel ({version}).", version=__version__))
            return
        self._update_release = release
        open_page = lambda: QDesktopServices.openUrl(QUrl(release.page))  # noqa: E731
        if not updater.is_frozen() or not release.asset_url or \
                (not updater.is_installed() and not updater.can_replace_portable()):
            # Kendini güncelleyemiyor (geliştirme kopyası, yazılamayan klasör…): sürüm sayfasını göster
            self.notify(tr("Yeni sürüm var: MCBShot {version}. İndirmek için tıklayın.", version=release.version),
                        ms=8000, on_click=open_page)
            return
        if manual:
            self.notify(tr("Yeni sürüm indiriliyor: MCBShot {version}…", version=release.version))
        self._update_busy = True
        updater.run_async(lambda: updater.download(release),
                          lambda path, err: self._on_update_downloaded(path, err, manual))

    def _on_update_downloaded(self, path, error, manual: bool) -> None:
        self._update_busy = False
        release = self._update_release
        if error or path is None or release is None:
            log.warning("Güncelleme indirilemedi: %s", error)
            if manual:
                self.notify(tr("Güncelleme indirilemedi: {error}", error=error),
                            QSystemTrayIcon.MessageIcon.Warning, 6000)
            return
        self._update_file = Path(path)
        self.act_install_update.setText(tr("Güncellemeyi yükle ({version})", version=release.version))
        self.act_install_update.setVisible(True)
        if self.settings.get("update_mode") == "auto" and not manual:
            self._auto_install()
        elif manual or not self._update_asked:
            self._offer_update()

    def _busy(self) -> bool:
        return (self._session is not None or self._scroll_job is not None or bool(self._editors)
                or QApplication.activeModalWidget() is not None)

    def _auto_install(self) -> None:
        if self._update_file is None:
            return
        if self._busy():
            QTimer.singleShot(UPDATE_RETRY_MS, self._auto_install)
            return
        self.install_update()

    def _offer_update(self) -> None:
        release = self._update_release
        if release is None or self._update_file is None:
            return
        if QApplication.activeModalWidget() is not None or self._session is not None:
            QTimer.singleShot(60_000, self._offer_update)   # başka bir pencere/yakalama açıkken araya girme
            return
        self._update_asked = True
        box = QMessageBox()
        box.setWindowTitle(tr("MCBShot güncellemesi"))
        box.setWindowIcon(icons.app_icon())
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(tr("MCBShot {version} hazır (şu an kullandığınız: {current}).",
                       version=release.version, current=__version__))
        box.setInformativeText(tr("Yükleme sırasında MCBShot kapanıp birkaç saniye içinde yeniden açılır."))
        notes = updater.notes_for_language(release.notes, i18n.language())
        if notes:
            box.setDetailedText(notes)
        install_btn = box.addButton(tr("Şimdi yükle"), QMessageBox.ButtonRole.AcceptRole)
        page_btn = box.addButton(tr("Sürüm sayfası"), QMessageBox.ButtonRole.HelpRole)
        box.addButton(tr("Sonra"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install_btn)
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        box.exec()
        clicked = box.clickedButton()
        if clicked is page_btn:
            QDesktopServices.openUrl(QUrl(release.page))
        elif clicked is install_btn:
            self.install_update()

    def install_update(self) -> None:
        if self._update_file is None or not self._update_file.exists():
            self._update_file = None
            self.act_install_update.setVisible(False)
            self.check_updates(manual=True)
            return
        try:
            updater.install(self._update_file)
        except OSError as ex:
            log.exception("Güncelleme başlatılamadı")
            self.notify(tr("Güncelleme başlatılamadı: {error}", error=ex), QSystemTrayIcon.MessageIcon.Warning, 6000)
            return
        log.info("Güncelleme başlatıldı: %s", self._update_file)
        self.quit()

    def restart(self) -> None:
        args = sys.argv[1:] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])] + sys.argv[1:]
        args = [a for a in args if a != "--wait-lock"] + ["--wait-lock"]
        QProcess.startDetached(sys.executable, args)
        self.quit()

    # ---- yakalama ----
    def start_delayed_capture(self) -> None:
        if self._session is not None:
            return
        delay = max(1, int(self.settings.get("delay_seconds")))
        self.tray.setToolTip(tr("{app}: {delay} sn sonra ekran görüntüsü alınacak…", app=APP_NAME, delay=delay))
        self._delay_timer.start(delay * 1000)

    def start_capture(self, scroll_mode: bool = False) -> None:
        if self._session is not None or self._scroll_job is not None:
            return
        self._update_labels()
        try:
            shots = capture_all(allow_span=bool(self.settings.get("span_monitors")))
        except Exception:
            log.exception("Ekran yakalanamadı")
            self.notify(tr("Ekran yakalanamadı. Ayrıntılar günlük dosyasında."),
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
                self.notify(error, QSystemTrayIcon.MessageIcon.Warning, 8000)
                return
            text = result.text.strip()
            if not text:
                self.notify(tr("Seçili alanda yazı bulunamadı."))
                return
            export.copy_text(text)
            if entry_id and self.history.get(entry_id):
                self.history.set_ocr_text(entry_id, text)
            preview = text if len(text) <= 120 else text[:117] + "…"
            msg = tr("Metin panoya kopyalandı:\n{text}", text=preview)
            if result.fallback:
                msg += "\n\n" + tr(ocr.FALLBACK_HINT)
            self.notify(msg, ms=6000)
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
        notes = {"limit": tr(" En fazla uzunluğa ulaşıldığı için durduruldu."),
                 "nomatch": tr(" Sayfanın bir kısmı eşleştirilemediği için orada durduruldu "
                               "(sayfada hareketli içerik olabilir).")}
        export.copy_image(image)
        try:
            entry_id = self.history.add(image, [], image, self._scroll_dpr)
        except Exception:
            log.exception("Kaydırmalı görüntü geçmişe eklenemedi")
            entry_id = ""
        self.notify(tr("Uzun ekran görüntüsü hazır ({w}×{h}) ve panoya kopyalandı. Düzenleyicide açıldı.",
                       w=image.width(), h=image.height()) + notes.get(reason, ""), ms=6000)
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
        def show_in_folder():
            if os.path.exists(path):
                subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        self.notify(tr("Kaydedildi: {name}\nKlasörde göstermek için tıklayın.", name=os.path.basename(path)),
                    on_click=show_in_folder)

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
        updater.cancel_all()
        # Arka planda süren OCR/indirme işleri bitmeden süreç kapanırsa Windows uygulamayı çökertir
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


def _install_qt_translations(app: QApplication) -> None:
    """Qt'nin kendi düğmeleri (Evet/Hayır, dosya penceresi...) da seçilen dilde olsun."""
    if i18n.language() != "tr":
        return
    translator = QTranslator(app)
    if translator.load("qtbase_tr", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)


def main() -> int:
    if "--selftest" in sys.argv:
        from .selftest import run
        return run()
    log_path = _setup_logging()
    log.info("MCBShot %s başlıyor", __version__)
    settings = Settings()
    i18n.set_language(settings.get("language"))

    def excepthook(exc_type, exc, tb):
        log.error("Beklenmeyen hata:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        if QApplication.instance() is not None:
            QMessageBox.critical(None, APP_NAME, tr("Beklenmeyen bir hata oluştu:\n{error}\n\nAyrıntılar: {log}",
                                                    error=exc, log=log_path))

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
    _install_qt_translations(app)

    lock = QLockFile(os.path.join(QDir.tempPath(), "MCBShot.lock"))
    # Yeniden başlatmada eski kopyanın kapanmasını bekle
    if not lock.tryLock(15000 if "--wait-lock" in sys.argv else 100):
        QMessageBox.information(None, APP_NAME, tr("MCBShot zaten çalışıyor.\n"
                                                   "Saatin yanındaki sistem tepsisinde simgesini bulabilirsiniz."))
        return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_NAME, tr("Sistem tepsisi bulunamadı."))
        return 1

    controller = MCBShotApp(app, settings)  # noqa: F841 (uygulama boyunca yaşamalı)
    code = app.exec()
    lock.unlock()
    return code
