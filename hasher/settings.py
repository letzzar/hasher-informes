"""Último estado de la aplicación, guardado en la carpeta de configuración del usuario.

Windows: %APPDATA%\\Hasher Informes\\settings.json
macOS:   ~/Library/Application Support/Hasher Informes/settings.json
Linux:   $XDG_CONFIG_HOME/hasher-informes/settings.json (por defecto ~/.config)
"""
import json
import os
import sys

from . import APP_NAME

# Solo se recuerdan datos estables; los datos de cada caso (referencia, denunciante,
# soporte, observaciones) no se guardan para no arrastrarlos al caso siguiente.
DEFAULTS = {
    "language": "es",
    "theme": "",  # "" = seguir el tema del sistema la primera vez
    "source": "",
    "dest": "",
    "operator": "",
    "include_hidden": False,
    "geometry": "",
}


def config_dir():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        return os.path.join(base, APP_NAME)
    if sys.platform == "darwin":
        return os.path.expanduser(os.path.join("~", "Library", "Application Support", APP_NAME))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser(os.path.join("~", ".config"))
    return os.path.join(base, "hasher-informes")


def settings_path():
    return os.path.join(config_dir(), "settings.json")


def load():
    data = dict(DEFAULTS)
    try:
        with open(settings_path(), encoding="utf-8") as f:
            stored = json.load(f)
        data.update({k: v for k, v in stored.items() if k in DEFAULTS and type(v) is type(DEFAULTS[k])})
    except (OSError, ValueError):
        pass  # primera ejecución o fichero dañado: valores por defecto
    return data


def save(data):
    """Guarda sin interrumpir nunca la aplicación si la carpeta no es escribible."""
    try:
        os.makedirs(config_dir(), exist_ok=True)
        tmp = settings_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: data[k] for k in DEFAULTS if k in data}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, settings_path())
    except OSError:
        pass
