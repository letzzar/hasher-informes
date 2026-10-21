# PROYECTO: Hasher Informes — Informe pericial de soportes digitales

## 1. Objetivo
Dejar constancia fehaciente de **qué archivos aporta un denunciante** en un soporte digital (carpeta, pendrive, DVD, disco externo), generando un informe que identifique cada archivo de forma unívoca mediante su hash **SHA-256**, de modo que en cualquier momento posterior se pueda verificar que los archivos no han sido alterados.

## 2. Requisitos
| Requisito | Decisión |
|---|---|
| Plataformas | Windows 10/11, macOS y Linux, cada uno en x86-64 y arm64 |
| Distribución | Portable, sin instalación ni permisos de administrador. Windows: un único `.exe`; macOS: `.app` en `.zip`; Linux: binario único en `.tar.gz` (PyInstaller). |
| Lenguaje | Python 3.13 |
| Interfaz | Tkinter/ttk con tema **sv-ttk** (claro/oscuro), tema inicial según el sistema (**darkdetect**) |
| Idiomas | Español e inglés (interfaz e informe), `hasher/i18n.py` |
| PDF | ReportLab, con fuente TrueType del sistema (Arial / DejaVu / Liberation); si no hay, Helvetica |
| Salidas | `Informe_<id>_<fecha>.pdf` y `.txt` (`Report_…` en inglés) en la carpeta elegida |
| Licencia | GPL-3.0 — repositorio https://github.com/letzzar/hasher-informes |
| Autor | Victor «Letzzar» Gallego (Acerca de y propiedades del `.exe`) |

## 3. Flujo de usuario
1. El operador abre la aplicación (se restaura el último estado guardado).
2. Selecciona el **origen**: botón "Carpeta…" o una **unidad** de la lista desplegable (detecta pendrives, DVD y discos; en macOS `/Volumes`, en Linux `/media`, `/run/media`, `/mnt`).
   - Casilla **"Incluir archivos ocultos y de sistema"** (desmarcada por defecto). Se consideran ocultos los que tienen atributo oculto o de sistema de Windows (Thumbs.db, desktop.ini, System Volume Information, $RECYCLE.BIN…), la marca oculta de macOS y los que empiezan por punto (.DS_Store, ._*, .Spotlight-V100, .Trashes, .fseventsd). Una carpeta oculta excluida no se recorre. Nunca se borran ni modifican.
3. Rellena los datos del caso:
   - Nº de diligencias / referencia (obligatorio)
   - Operador / instructor
   - Aportado por (denunciante)
   - Descripción del soporte (p. ej. "Pendrive Kingston 16 GB negro")
   - Observaciones
4. Elige la **carpeta de destino** de los informes (no puede estar dentro del origen).
5. Pulsa **"Generar informe"**. Se muestra progreso (archivo actual, nº de archivos, bytes procesados) y puede **cancelar**.
6. Al terminar, se muestra un resumen y botones para abrir el PDF o la carpeta.

Menús: **Ver** (Tema claro/oscuro, Idioma) y **Ayuda** (Acerca de). En macOS van en la barra de menús del sistema; en Windows/Linux, en una barra dentro de la ventana con el estilo del tema.

## 4. Contenido del informe
### Cabecera
- Título "INFORME DE CONTENIDO DE SOPORTE DIGITAL"
- Datos del caso (punto 3)
- Fecha y hora de inicio y fin del análisis (hora local con zona horaria)
- Equipo, usuario del sistema, versión de Hasher Informes
- Origen analizado; datos del volumen: etiqueta, nº de serie (solo Windows), sistema de archivos, tipo de unidad
- Algoritmo: SHA-256

### Resumen
- Nº total de archivos, nº de carpetas, tamaño total
- Nº de archivos con error de lectura
- Archivos ocultos y de sistema: "Incluidos" o "Excluidos del informe (N archivos, M carpetas)"

### Relación de archivos (ordenada por ruta)
| Nº | Nombre (con su subcarpeta, si la hay) | Fecha creación | Tamaño (bytes) | SHA-256 |

Los archivos ilegibles aparecen con `ERROR: <motivo>` en la columna del hash.

### Pie / integridad
- En el PDF: SHA-256 del fichero TXT generado (permite verificar que el TXT es el emitido).
- Espacio para firma del operador.
- Numeración "Página X de Y".

## 5. Último estado
`hasher/settings.py` guarda `settings.json` en la carpeta de configuración del usuario:
Windows `%APPDATA%\Hasher Informes\`, macOS `~/Library/Application Support/Hasher Informes/`, Linux `$XDG_CONFIG_HOME/hasher-informes/` (`~/.config`).
Se recuerdan idioma, tema, origen, destino, operador, casilla de ocultos y tamaño/posición de ventana. **No** se guardan referencia, denunciante, descripción del soporte ni observaciones (son de cada caso).

## 6. Arquitectura
```
Hasher/
├── main.py                 # Punto de entrada (lanza la GUI)
├── icono.png               # Icono original
├── assets/                 # icono.ico / icono.icns / icono.png (generados)
├── hasher/
│   ├── __init__.py         # Nombre, versión, URL del repositorio
│   ├── core.py             # Escaneo, SHA-256, info de volumen/unidades (multiplataforma)
│   ├── report.py           # Generación TXT y PDF
│   ├── i18n.py             # Textos ES/EN
│   ├── settings.py         # Último estado
│   └── gui.py              # Interfaz, tema, idioma, Acerca de; hilo de trabajo + cola
├── scripts/
│   ├── build.py            # Compila y empaqueta para el sistema actual
│   └── make_icons.py       # Genera assets/ desde icono.png
├── tests/                  # unittest
├── docs/                   # Capturas para el README
├── .github/workflows/build.yml  # CI: 6 compilaciones + Release en etiquetas vX.Y.Z
├── build.bat, requirements.txt, LICENSE, README.md
├── CLAUDE.md / PROYECTO.md / SESSION_HANDOFF.md
```

## 7. Decisiones técnicas
- **Solo lectura:** apertura `rb`, lectura por bloques de 1 MiB (memoria constante para archivos grandes).
- **Rutas largas (Windows):** prefijo `\\?\` interno para rutas > 260 caracteres; en el informe se muestran sin él.
- **Enlaces simbólicos / uniones:** no se siguen (se evita recorrer fuera del origen y bucles).
- **Fechas:** creación = `st_birthtime` (Windows y macOS) en hora local con desfase UTC (ej. `2026-10-20 10:15:03 +02:00`). En Linux Python no la expone: se indica `N/D`.
- **Concurrencia:** el escaneo corre en un `threading.Thread`; la GUI consulta una `queue.Queue` con `after()`. Cancelación mediante `threading.Event`.
- **Destino:** se bloquea guardar dentro del origen (un DVD es de solo lectura y además se contaminaría la evidencia).
- **macOS:** la app no está firmada/notarizada por Apple (requiere cuenta de desarrollador); el README explica cómo abrirla.

## 8. Fuera de alcance (por ahora)
- Verificación posterior de un soporte contra un informe previo.
- Imágenes forenses bit a bit del dispositivo (E01/dd).
- Otros algoritmos (MD5/SHA-1).
- Firma digital del PDF.
- Firma de código de los ejecutables (Authenticode / Apple notarization).
