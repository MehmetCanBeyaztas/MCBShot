"""GitHub Releases üzerinden güncelleme denetimi, indirme ve yükleme.

Kurulumla gelen kopya yeni kurulum dosyasını (MCBShot-Setup-x.y.z.exe) sessizce çalıştırır;
kurulum bitince program yeniden açılır. Taşınabilir kopya yeni MCBShot.exe'yi indirir ve
program kapandıktan sonra eskisinin yerine koyar. Ağ işleri arka plan iş parçacığında çalışır.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal

from . import APP_NAME, __version__
from .i18n import tr

log = logging.getLogger(APP_NAME)

REPO = "MehmetCanBeyaztas/MCBShot"
# Sınama için başka bir adres verilebilir (indirilen dosyalar yine bu deponun sürümlerinden olmalı)
API_URL = os.environ.get("MCBSHOT_UPDATE_API") or f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
TIMEOUT = 20

_cancel = threading.Event()   # program kapanırken süren indirmeyi durdurur


@dataclass
class Release:
    version: str
    notes: str
    page: str
    asset_name: str
    asset_url: str
    size: int
    sha256: str | None


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Sayı olmayan kısımda durur ('1.2.0-beta' -> (1, 2, 0))."""
    parts = []
    for p in text.strip().lstrip("vV").split("."):
        m = re.match(r"\d+", p)
        if not m:
            break
        parts.append(int(m.group()))
    return tuple(parts)


def is_newer(version: str, current: str = __version__) -> bool:
    return parse_version(version) > parse_version(current)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_installed() -> bool:
    """Kurulum programıyla mı kuruldu (yanında kaldırma programı var mı)?"""
    return is_frozen() and (Path(sys.executable).parent / "unins000.exe").exists()


def _wanted_asset(name: str) -> bool:
    if is_installed():
        return name.lower().startswith("mcbshot-setup-") and name.lower().endswith(".exe")
    return name.lower() == "mcbshot.exe"


def _request(url: str):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"{APP_NAME}/{__version__}",
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def release_from_json(data: dict) -> Release | None:
    """GitHub API yanıtından bu kopyaya uygun dosyayı seçer; yoksa None."""
    tag = data.get("tag_name") or ""
    if not parse_version(tag):
        raise ValueError(tr("Sunucudan beklenmeyen yanıt"))
    for asset in data.get("assets") or []:
        url = asset.get("browser_download_url") or ""
        if not _wanted_asset(asset.get("name", "")) or not url.startswith(DOWNLOAD_PREFIX):
            continue
        digest = asset.get("digest") or ""
        return Release(
            version=tag.lstrip("vV"), notes=data.get("body") or "", page=data.get("html_url") or RELEASES_URL,
            asset_name=asset["name"], asset_url=url, size=int(asset.get("size") or 0),
            sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None)
    return Release(version=tag.lstrip("vV"), notes=data.get("body") or "",
                   page=data.get("html_url") or RELEASES_URL, asset_name="", asset_url="", size=0, sha256=None)


def fetch_latest() -> Release | None:
    with _request(API_URL) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return release_from_json(data)


def download_dir() -> Path:
    path = Path(tempfile.gettempdir()) / f"{APP_NAME}-update"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download(release: Release) -> Path:
    """Dosyayı indirip boyutunu ve SHA-256 özetini doğrular."""
    target = download_dir() / release.asset_name
    if target.exists() and _verify(target, release):
        return target   # daha önce indirilmiş
    part = target.with_name(target.name + ".part")
    sha = hashlib.sha256()
    with _request(release.asset_url) as resp, open(part, "wb") as f:
        while True:
            if _cancel.is_set():
                raise InterruptedError("cancelled")
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            sha.update(chunk)
            f.write(chunk)
    if not _verify(part, release, sha.hexdigest()):
        part.unlink(missing_ok=True)
        raise OSError(tr("İndirilen dosya doğrulanamadı"))
    os.replace(part, target)
    return target


def _verify(path: Path, release: Release, digest: str | None = None) -> bool:
    if release.size and path.stat().st_size != release.size:
        return False
    if release.sha256:
        if digest is None:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return digest == release.sha256
    return True


def can_replace_portable() -> bool:
    folder = Path(sys.executable).parent
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".mcbshot-write-test-"):
            pass
        return True
    except OSError:
        return False


def install(path: Path) -> None:
    """Güncellemeyi başlatır. Çağıran program hemen ardından kapanmalı.

    İş, program tamamen kapanana kadar bekleyen gizli bir PowerShell'e bırakılır (tek dosyalık
    exe'de iki süreç var: açıcı + asıl program). Böylece kurulum, çalışan programı kapatmak için
    Windows'un 30 sn'lik zaman aşımını beklemez.
    """
    pids = ",".join(str(p) for p in {os.getpid(), os.getppid()})
    wait = f"Wait-Process -Id {pids} -Timeout 30 -ErrorAction SilentlyContinue; "
    env = dict(os.environ, MCB_NEW=str(path), MCB_TARGET=sys.executable)
    if is_installed():
        args = "'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/SP-','/relaunch=1'"
        # "Tüm kullanıcılar" için (Program Files'a) kurulduysa aynı yere kurulsun (yönetici izni ister)
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files").lower()
        if str(Path(sys.executable)).lower().startswith(program_files):
            args += ",'/ALLUSERS'"
        script = wait + f"Start-Process -FilePath $env:MCB_NEW -ArgumentList {args}"
    else:
        # Taşınabilir: dosya serbest kalınca yeni exe'yi eskisinin yerine koy ve başlat
        script = wait + ("$n = 0; while ($n -lt 60) { "
                         "try { Move-Item -LiteralPath $env:MCB_NEW -Destination $env:MCB_TARGET -Force "
                         "-ErrorAction Stop; break } catch { $n++; Start-Sleep -Milliseconds 500 } }; "
                         "Start-Process -FilePath $env:MCB_TARGET")
    # DETACHED_PROCESS ve -WindowStyle Hidden kullanılmamalı: PowerShell betiği hiç çalıştırmadan kapanıyor
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                      "-Command", script], env=env, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cancel_all() -> None:
    _cancel.set()


def notes_for_language(notes: str, lang: str) -> str:
    """Sürüm notları iki dilli: '<a id="english"></a>' işaretinden sonrası İngilizce."""
    marker = '<a id="english"></a>'
    if marker not in notes:
        return notes
    tr_part, en_part = notes.split(marker, 1)
    text = en_part if lang == "en" else tr_part
    # Dil bağlantılarını ve ayırıcıyı at
    lines = [ln for ln in text.strip().splitlines() if not ln.startswith("**Türkçe**") and ln.strip() != "---"]
    return "\n".join(lines).strip()


# ---- arka plan işi ----
class _Signals(QObject):
    done = Signal(object, object)   # (sonuç, hata mesajı | None)


class _Task(QRunnable):
    def __init__(self, fn, signals: _Signals):
        super().__init__()
        self.fn = fn
        self.signals = signals

    def run(self):
        try:
            self.signals.done.emit(self.fn(), None)
        except InterruptedError:
            pass
        except Exception as ex:   # ağ hatası programı hiçbir zaman çökertmesin
            log.warning("Güncelleme işi başarısız: %s", ex)
            self.signals.done.emit(None, str(ex) or ex.__class__.__name__)


_active: set[_Signals] = set()


def run_async(fn, callback) -> None:
    """fn() arka planda çalışır; bitince callback(sonuç, hata) arayüz iş parçacığında çağrılır."""
    signals = _Signals()
    _active.add(signals)

    def finished(result, error):
        _active.discard(signals)
        callback(result, error)

    signals.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    QThreadPool.globalInstance().start(_Task(fn, signals))
