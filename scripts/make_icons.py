"""Genera los iconos de la aplicación a partir de icono.png (requiere Pillow).

    python scripts/make_icons.py

Salida en assets/: icono.ico (Windows), icono.icns (macOS) e icono.png (256 px, ventana/Linux).
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

os.makedirs(ASSETS, exist_ok=True)
src = Image.open(os.path.join(ROOT, "icono.png")).convert("RGBA")
src.save(os.path.join(ASSETS, "icono.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
src.resize((1024, 1024), Image.LANCZOS).save(os.path.join(ASSETS, "icono.icns"))
src.resize((256, 256), Image.LANCZOS).save(os.path.join(ASSETS, "icono.png"), optimize=True)
print("Iconos generados en", ASSETS)
