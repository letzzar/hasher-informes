# SESSION HANDOFF

## Estado actual (2026-10-21)
Versión **1.1.0** de **Hasher Informes** publicada.
- Repositorio público: https://github.com/letzzar/hasher-informes (GPL-3.0, rama `main`)
- Release: https://github.com/letzzar/hasher-informes/releases/tag/v1.1.0 con 6 paquetes
  (Windows/macOS/Linux × x86-64/arm64), todos compilados y con tests en verde en GitHub Actions.

### Completado
- v1.0.0: escaneo de solo lectura + SHA-256, informe PDF/TXT (Nº | Nombre | Fecha creación | Tamaño | SHA-256), GUI Tkinter, casilla de ocultos/sistema (por defecto excluidos; el informe indica cuántos se omitieron).
- v1.1.0:
  - Icono (`icono.png` → `assets/` con `scripts/make_icons.py`) en ventana, `.exe` y `.app`.
  - Último estado en `settings.json` (AppData / Application Support / ~/.config). No guarda datos del caso (referencia, denunciante, soporte, observaciones).
  - Tema claro/oscuro (sv-ttk; inicial según el sistema), barra de título oscura en Windows y barra de menús propia (en macOS, menú nativo).
  - Idiomas español/inglés (interfaz e informe; archivos `Informe_…` / `Report_…`).
  - Acerca de con la firma "By Victor «Letzzar» Gallego", enlace al repositorio y licencia; propiedades del `.exe` con autor y copyright.
  - Núcleo multiplataforma; CI `.github/workflows/build.yml` (push a main → artefactos; etiqueta `vX.Y.Z` → Release).
  - README con capturas (`docs/`), LICENSE GPL-3.0.
- Tests: 15 (unittest) en verde en Windows local y en los 6 runners de CI.

### Pendiente / a validar por el Director
- Probar el `.exe` con un pendrive y un DVD reales.
- Probar los paquetes de macOS, Linux y Windows ARM en equipos reales (solo validados en CI).
- Firma de código (Authenticode / notarización de Apple) si se quiere evitar avisos de seguridad.
- Opcional: fijar el runner del job `release` a `ubuntu-24.04` (GitHub avisa de que `ubuntu-latest` migra a Ubuntu 26).

### Notas para la próxima sesión
- Sincronizar con el NAS al acabar cada tarea: `powershell -File sync_nas.ps1` → `Y:\Mi software\Hasher` (aditivo, no borra).
- En este equipo el Bash de Git falla al hacer fork; usar PowerShell.
- El filtro de seguridad de comandos bloquea algunas órdenes PowerShell que combinan `cd "D:\Software mio\…"` con ciertas palabras (`Remove-Item`, `git remote`, `--renormalize`…): usar `git -C "<ruta>"` y comandos separados.
- Si la compilación local falla con "acceso denegado", cerrar instancias abiertas de `Hasher Informes.exe` (el modo onefile deja un proceso hijo).
- Publicar versión: subir `__version__` en `hasher/__init__.py`, commit, `git tag -a vX.Y.Z` y `git push origin vX.Y.Z`.
