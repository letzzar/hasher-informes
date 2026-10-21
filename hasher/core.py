"""Escaneo de solo lectura de un origen (carpeta o unidad) y cálculo de SHA-256."""
import ctypes
import glob
import hashlib
import os
import stat
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime

from .i18n import tr

CHUNK = 1024 * 1024  # 1 MiB
PROGRESS_EVERY = 64 * CHUNK  # notificar progreso dentro de archivos grandes
WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"


class Cancelled(Exception):
    pass


@dataclass
class FileEntry:
    rel_path: str
    size: int = 0
    created: str = ""
    sha256: str = ""
    error: str = ""


@dataclass
class ScanResult:
    root: str
    entries: list = field(default_factory=list)  # FileEntry, ordenadas por ruta
    n_dirs: int = 0
    skipped: list = field(default_factory=list)  # (ruta relativa, motivo): enlaces y carpetas ilegibles
    include_hidden: bool = True
    hidden_files: int = 0  # ocultos/sistema excluidos del informe
    hidden_dirs: int = 0

    @property
    def total_bytes(self):
        return sum(e.size for e in self.entries)

    @property
    def n_errors(self):
        return sum(1 for e in self.entries if e.error)


def format_ts(ts):
    """Marca de tiempo -> 'AAAA-MM-DD HH:MM:SS +HH:MM' en hora local."""
    dt = datetime.fromtimestamp(ts).astimezone()
    off = dt.strftime("%z")  # +0200
    return f"{dt:%Y-%m-%d %H:%M:%S} {off[:3]}:{off[3:]}"


def _long(path):
    """En Windows, prefijo \\\\?\\ para soportar rutas de más de 260 caracteres."""
    path = os.path.abspath(path)
    if not WINDOWS or path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


def _is_link(entry):
    return entry.is_symlink() or entry.is_junction()


HIDDEN_ATTRS = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0) | getattr(stat, "FILE_ATTRIBUTE_SYSTEM", 0)


def is_hidden(entry):
    """Nombre con punto inicial (.DS_Store, ._*, .Trashes), atributo oculto/sistema de Windows
    o marca oculta de macOS (UF_HIDDEN)."""
    if entry.name.startswith("."):
        return True
    try:
        st = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    if getattr(st, "st_file_attributes", 0) & HIDDEN_ATTRS:
        return True
    return bool(getattr(st, "st_flags", 0) & getattr(stat, "UF_HIDDEN", 0))


def _created(st):
    """Fecha de creación; Linux no la expone en Python (N/D)."""
    ts = getattr(st, "st_birthtime", None)
    return format_ts(ts) if ts else tr("na")


def _enumerate(root_long, result, cancel):
    """Recorre el árbol sin seguir enlaces. Devuelve [(ruta_larga, FileEntry)]."""
    found = []
    prefix_len = len(root_long.rstrip(os.sep)) + 1
    stack = [root_long]
    while stack:
        if cancel.is_set():
            raise Cancelled()
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                items = list(it)
        except OSError as exc:
            result.skipped.append((current[prefix_len:] or ".", tr("scan.unreadable_dir", e=exc.strerror or exc)))
            continue
        for entry in items:
            rel = entry.path[prefix_len:]
            if not result.include_hidden and is_hidden(entry):
                if entry.is_dir(follow_symlinks=False):
                    result.hidden_dirs += 1  # no se entra en ella
                else:
                    result.hidden_files += 1
            elif _is_link(entry):
                result.skipped.append((rel, tr("scan.link")))
            elif entry.is_dir(follow_symlinks=False):
                result.n_dirs += 1
                stack.append(entry.path)
            else:
                fe = FileEntry(rel_path=rel)
                try:
                    st = entry.stat(follow_symlinks=False)
                    fe.size = st.st_size
                    fe.created = _created(st)
                    if not stat.S_ISREG(st.st_mode):
                        fe.error = tr("scan.not_regular")
                except OSError as exc:
                    fe.error = tr("scan.meta_error", e=exc.strerror or exc)
                found.append((entry.path, fe))
    found.sort(key=lambda x: x[1].rel_path.lower())
    return found


def scan(root, progress=None, cancel=None, include_hidden=True):
    """Escanea `root` en solo lectura y calcula el SHA-256 de cada archivo.

    progress(done_files, total_files, done_bytes, total_bytes, current_rel) se llama
    periódicamente desde el hilo que ejecuta scan(). `cancel` es un threading.Event.
    Con include_hidden=False los ocultos/sistema no se listan, solo se cuentan.
    """
    cancel = cancel or threading.Event()
    progress = progress or (lambda *a: None)
    result = ScanResult(root=os.path.abspath(root), include_hidden=include_hidden)

    found = _enumerate(_long(root), result, cancel)
    total_files = len(found)
    total_bytes = sum(fe.size for _, fe in found)
    done_bytes = 0

    for i, (path, fe) in enumerate(found):
        progress(i, total_files, done_bytes, total_bytes, fe.rel_path)
        if not fe.error:
            h = hashlib.sha256()
            read = 0
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(CHUNK):
                        if cancel.is_set():
                            raise Cancelled()
                        h.update(chunk)
                        read += len(chunk)
                        if read % PROGRESS_EVERY == 0:
                            progress(i, total_files, done_bytes + read, total_bytes, fe.rel_path)
                fe.sha256 = h.hexdigest()
            except OSError as exc:
                fe.error = tr("scan.read_error", e=exc.strerror or exc)
        done_bytes += fe.size
        result.entries.append(fe)

    progress(total_files, total_files, total_bytes, total_bytes, "")
    return result


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


# --- Información de unidades y volúmenes ------------------------------------

DRIVE_TYPES = {2: "drive.removable", 3: "drive.fixed", 4: "drive.network", 5: "drive.cdrom", 6: "drive.ram"}
REMOVABLE_ROOTS = ("/Volumes/", "/media/", "/run/media/", "/mnt/")


def _win_drive_type(root):
    return tr(DRIVE_TYPES.get(ctypes.windll.kernel32.GetDriveTypeW(root), "drive.unknown"))


def _win_volume_info(path):
    k32 = ctypes.windll.kernel32
    vol_path = ctypes.create_unicode_buffer(300)
    if not k32.GetVolumePathNameW(os.path.abspath(path), vol_path, 300):
        return {}
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_uint32()
    if not k32.GetVolumeInformationW(vol_path.value, label, 261, ctypes.byref(serial), None, None, fs, 261):
        return {}
    s = serial.value
    return {
        "volume": vol_path.value,
        "label": label.value or tr("drive.no_label"),
        "serial": f"{s >> 16:04X}-{s & 0xFFFF:04X}",
        "filesystem": fs.value,
        "type": _win_drive_type(vol_path.value),
    }


def _mount_point(path):
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def _posix_filesystem(mount):
    """Tipo de sistema de archivos del punto de montaje (Linux: /proc/mounts; macOS: mount)."""
    try:
        if MACOS:
            out = subprocess.run(["mount"], capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():  # "/dev/disk4s1 on /Volumes/USB (msdos, local, ...)"
                dev_on, _, rest = line.partition(" on ")
                mnt, _, opts = rest.rpartition(" (")
                if mnt == mount:
                    return opts.split(",")[0]
        else:
            with open("/proc/mounts", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) > 2 and parts[1].replace("\\040", " ") == mount:
                        return parts[2]
    except OSError:
        pass
    return tr("na")


def _posix_volume_info(path):
    mount = _mount_point(path)
    removable = any(mount.startswith(r) for r in REMOVABLE_ROOTS)
    return {
        "volume": mount,
        "label": os.path.basename(mount) or tr("drive.no_label"),
        "serial": tr("na"),
        "filesystem": _posix_filesystem(mount),
        "type": tr("drive.removable" if removable else "drive.fixed"),
    }


def volume_info(path):
    """Datos del volumen que contiene `path`, o {} si no se pueden obtener."""
    try:
        return _win_volume_info(path) if WINDOWS else _posix_volume_info(path)
    except OSError:
        return {}


def list_drives():
    """[(raíz, texto descriptivo)] de las unidades/volúmenes disponibles."""
    if WINDOWS:
        roots = os.listdrives()
    else:
        user = os.environ.get("USER", "")
        roots = ["/"] + sorted(set(glob.glob("/Volumes/*") + glob.glob(f"/media/{user}/*")
                                   + glob.glob(f"/run/media/{user}/*") + glob.glob("/mnt/*")))
    drives = []
    for root in roots:
        info = volume_info(root)
        if info and (WINDOWS or info["volume"] == os.path.realpath(root)):
            drives.append((root, f"{root}  {info['label']}  ({info['type']}, {info['filesystem']})"))
        elif WINDOWS:
            drives.append((root, f"{root}  ({_win_drive_type(root)}, {tr('drive.no_media')})"))
    return drives
