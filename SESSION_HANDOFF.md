# SESSION HANDOFF

## Estado actual (2026-10-21)
Versión **1.1.0** de **Hasher Informes**. Repositorio público: https://github.com/letzzar/hasher-informes (GPL-3.0).

### Completado
- v1.0.0: escaneo de solo lectura + SHA-256, informe PDF/TXT (Nº | Nombre | Fecha creación | Tamaño | SHA-256), GUI Tkinter, casilla de ocultos/sistema (por defecto excluidos, el informe indica cuántos).
- v1.1.0:
  - Icono (`icono.png` → `assets/` con `scripts/make_icons.py`) en ventana, `.exe` y `.app`.
  - Último estado en `settings.json` (AppData / Application Support / ~/.config). No guarda datos del caso.
  - Tema claro/oscuro (sv-ttk; inicial según el sistema) con barra de título oscura en Windows y barra de menús propia.
  - Idiomas español/inglés (interfaz e informe).
  - Acerca de con la firma "By Victor «Letzzar» Gallego", enlace al repositorio y licencia; propiedades del `.exe` con autor y copyright.
  - Núcleo multiplataforma (Windows/macOS/Linux) y CI en GitHub Actions para x86-64 y arm64 con Release al etiquetar.
- Tests: 15 (unittest) en verde en Windows.

### Pendiente / a validar por el Director
- Probar el `.exe` con un pendrive y un DVD reales.
- Probar los paquetes de macOS y Linux en equipos reales (solo se han validado en CI).
- Firma de código (Authenticode / notarización de Apple) si se quiere evitar avisos de seguridad.
