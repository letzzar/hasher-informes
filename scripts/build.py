"""Compila el ejecutable portable para el sistema y arquitectura actuales.

    python scripts/build.py            -> dist/ con el ejecutable
    python scripts/build.py --package  -> además, el paquete de distribución en dist/release/

Windows: "Hasher Informes.exe" (un único archivo)
macOS:   "Hasher Informes.app" (comprimido en .zip)
Linux:   "hasher-informes" (un único archivo, comprimido en .tar.gz)
"""
import os
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from hasher import APP_NAME, __version__  # noqa: E402

AUTHOR = "Victor «Letzzar» Gallego"
DIST = os.path.join(ROOT, "dist")
BUILD = os.path.join(ROOT, "build")


def arch():
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def os_name():
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def write_version_file(path):
    """Propiedades del .exe de Windows (autor, versión, licencia)."""
    nums = (tuple(int(x) for x in __version__.split(".")) + (0, 0, 0))[:4]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[
    StringFileInfo([StringTable('040A04B0', [
      StringStruct('CompanyName', '{AUTHOR}'),
      StringStruct('FileDescription', '{APP_NAME} - Informe pericial de soportes digitales'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('LegalCopyright', '© 2026 {AUTHOR}. GPL-3.0'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x040A, 1200])])
  ]
)
""")


def build():
    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(DIST, ignore_errors=True)
    assets = os.path.join(ROOT, "assets")
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", APP_NAME if sys.platform != "linux" else "hasher-informes",
        "--add-data", f"{os.path.join(assets, 'icono.png')}{os.pathsep}assets",
        "--collect-data", "sv_ttk",
        "--distpath", DIST, "--workpath", BUILD, "--specpath", BUILD,
    ]
    if sys.platform == "win32":
        version_file = os.path.join(BUILD, "version_info.txt")
        os.makedirs(BUILD, exist_ok=True)
        write_version_file(version_file)
        args += ["--onefile", "--icon", os.path.join(assets, "icono.ico"), "--version-file", version_file]
    elif sys.platform == "darwin":
        args += ["--onedir", "--icon", os.path.join(assets, "icono.icns"),
                 "--osx-bundle-identifier", "com.letzzar.hasherinformes"]
    else:
        args += ["--onefile"]
    args.append(os.path.join(ROOT, "main.py"))
    subprocess.run(args, check=True, cwd=ROOT)


def package():
    """Empaqueta el resultado con un nombre que incluye versión, sistema y arquitectura."""
    out = os.path.join(DIST, "release")
    os.makedirs(out, exist_ok=True)
    stem = f"HasherInformes-{__version__}-{os_name()}-{arch()}"
    if sys.platform == "win32":
        target = os.path.join(out, stem + ".exe")
        shutil.copy2(os.path.join(DIST, APP_NAME + ".exe"), target)
    elif sys.platform == "darwin":
        target = os.path.join(out, stem + ".zip")
        subprocess.run(["ditto", "-c", "-k", "--keepParent", os.path.join(DIST, APP_NAME + ".app"), target],
                       check=True)
    else:
        target = os.path.join(out, stem + ".tar.gz")
        with tarfile.open(target, "w:gz") as tar:
            tar.add(os.path.join(DIST, "hasher-informes"), arcname=f"{stem}/hasher-informes")
            tar.add(os.path.join(ROOT, "assets", "icono.png"), arcname=f"{stem}/hasher-informes.png")
            tar.add(os.path.join(ROOT, "LICENSE"), arcname=f"{stem}/LICENSE")
    print("Paquete:", target)


if __name__ == "__main__":
    build()
    if "--package" in sys.argv:
        package()
