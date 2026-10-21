"""Generación del informe pericial en TXT y PDF."""
import getpass
import os
import platform
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (KeepTogether, LongTable, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from . import APP_NAME, __version__
from .core import format_ts, scan, sha256_file, volume_info
from .i18n import get_language, tr


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n} bytes" if unit == "bytes" else f"{n:.2f} {unit}"
        n /= 1024


def fmt_int(n):
    s = f"{n:,}"
    return s if get_language() == "en" else s.replace(",", ".")


def header_fields(meta, result):
    """Pares (etiqueta, valor) comunes a TXT y PDF."""
    case = meta["case"]
    vol = meta.get("volume") or {}
    rows = [
        (tr("rep.reference"), case.get("reference", "")),
        (tr("rep.operator"), case.get("operator", "")),
        (tr("rep.provided_by"), case.get("provided_by", "")),
        (tr("rep.media"), case.get("media", "")),
        (tr("rep.notes"), case.get("notes", "")),
        (tr("rep.source"), result.root),
    ]
    if vol:
        rows += [
            (tr("rep.volume"), tr("rep.volume_val", volume=vol["volume"], label=vol["label"])),
            (tr("rep.serial"), vol["serial"]),
            (tr("rep.fs"), f"{vol['filesystem']} / {vol['type']}"),
        ]
    rows += [
        (tr("rep.start"), meta["start"]),
        (tr("rep.end"), meta["end"]),
        (tr("rep.host"), f"{meta['host']} / {meta['user']}"),
        (tr("rep.app"), f"{APP_NAME} {__version__}"),
        (tr("rep.algorithm"), "SHA-256"),
    ]
    return rows


def summary_fields(result):
    return [
        (tr("rep.files"), fmt_int(len(result.entries))),
        (tr("rep.dirs"), fmt_int(result.n_dirs)),
        (tr("rep.total_size"), f"{fmt_int(result.total_bytes)} bytes ({human_size(result.total_bytes)})"),
        (tr("rep.read_errors"), fmt_int(result.n_errors)),
        (tr("rep.skipped"), fmt_int(len(result.skipped))),
        (tr("rep.hidden"),
         tr("rep.hidden_in") if result.include_hidden else
         tr("rep.hidden_out", files=fmt_int(result.hidden_files), dirs=fmt_int(result.hidden_dirs))),
    ]


def _columns():
    return (tr("rep.col_n"), tr("rep.col_name"), tr("rep.col_created"), tr("rep.col_size"), "SHA-256")


# --- TXT ---------------------------------------------------------------------

def write_txt(path, meta, result):
    sep = "=" * 100
    lines = [sep, tr("rep.title"), sep, ""]
    width = max(len(k) for k, _ in header_fields(meta, result) + summary_fields(result))
    lines += [f"{k.ljust(width)} : {v}" for k, v in header_fields(meta, result)]
    lines += ["", tr("rep.summary").upper(), "-" * 100]
    lines += [f"{k.ljust(width)} : {v}" for k, v in summary_fields(result)]
    lines += ["", tr("rep.list").upper(), "-" * 100, " | ".join(_columns())]
    for i, e in enumerate(result.entries, 1):
        digest = e.sha256 or tr("rep.error", e=e.error)
        lines.append(f"{i} | {e.rel_path} | {e.created} | {e.size} | {digest}")
    if result.skipped:
        lines += ["", tr("rep.skipped").upper(), "-" * 100]
        lines += [f"{rel} | {reason}" for rel, reason in result.skipped]
    lines += ["", sep, tr("rep.end_of_report"), sep, ""]
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write("\n".join(lines))


# --- PDF ---------------------------------------------------------------------

_WIN_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
# (regular, negrita) con soporte de acentos y ñ, por orden de preferencia en cada sistema
SANS_CANDIDATES = [
    (os.path.join(_WIN_FONTS, "arial.ttf"), os.path.join(_WIN_FONTS, "arialbd.ttf")),
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf", "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]
MONO_CANDIDATES = [
    os.path.join(_WIN_FONTS, "consola.ttf"),
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
]


def _register_fonts():
    """Primera fuente TrueType disponible del sistema; si no hay ninguna, fuentes base."""
    regular, bold, mono = "Helvetica", "Helvetica-Bold", "Courier"
    for reg_path, bold_path in SANS_CANDIDATES:
        if os.path.exists(reg_path) and os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont("Sans", reg_path))
                pdfmetrics.registerFont(TTFont("Sans-Bold", bold_path))
                regular, bold = "Sans", "Sans-Bold"
                break
            except Exception:
                continue
    for path in MONO_CANDIDATES:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("Mono", path))
                mono = "Mono"
                break
            except Exception:
                continue
    return regular, bold, mono


class _NumberedCanvas(canvas.Canvas):
    """Canvas que añade 'Página X de Y' y la referencia en cada página."""
    reference = ""
    font = "Helvetica"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            w, _ = self._pagesize
            self.setFont(self.font, 7.5)
            self.setFillColor(colors.grey)
            self.drawString(15 * mm, 8 * mm, f"{tr('rep.title')} — {tr('rep.ref_footer', ref=self.reference)}")
            self.drawRightString(w - 15 * mm, 8 * mm, tr("rep.page", n=self._pageNumber, total=total))
            super().showPage()
        super().save()


def write_pdf(path, meta, result, txt_path):
    regular, bold, mono = _register_fonts()
    st_title = ParagraphStyle("t", fontName=bold, fontSize=15, alignment=TA_CENTER, spaceAfter=8)
    st_h = ParagraphStyle("h", fontName=bold, fontSize=10.5, spaceBefore=8, spaceAfter=4,
                          textColor=colors.HexColor("#1F3A5F"))
    st_k = ParagraphStyle("k", fontName=bold, fontSize=8.5, leading=10.5)
    st_v = ParagraphStyle("v", fontName=regular, fontSize=8.5, leading=10.5, wordWrap="CJK")
    st_cell = ParagraphStyle("c", fontName=regular, fontSize=7, leading=8.5, wordWrap="CJK")
    st_num = ParagraphStyle("n", parent=st_cell, alignment=TA_RIGHT)
    st_hash = ParagraphStyle("hs", fontName=mono, fontSize=7, leading=8.5)
    st_err = ParagraphStyle("e", parent=st_cell, textColor=colors.HexColor("#B00020"))
    st_th = ParagraphStyle("th", fontName=bold, fontSize=7.5, leading=9, textColor=colors.white)

    def p(text, style):
        return Paragraph(escape(str(text)), style)

    def kv_table(rows):
        t = Table([[p(k, st_k), p(v, st_v)] for k, v in rows], colWidths=[60 * mm, None])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C4D6")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF2F8")),
        ]))
        return t

    story = [Paragraph(tr("rep.title"), st_title),
             Paragraph(tr("rep.analysis"), st_h), kv_table(header_fields(meta, result)),
             Paragraph(tr("rep.summary"), st_h), kv_table(summary_fields(result)),
             Paragraph(tr("rep.list"), st_h)]

    page_w = landscape(A4)[0] - 30 * mm
    widths = [12 * mm, None, 32 * mm, 24 * mm, 93 * mm]
    widths[1] = page_w - sum(w for w in widths if w)
    data = [[p(h, st_th) for h in _columns()]]
    for i, e in enumerate(result.entries, 1):
        digest = p(e.sha256, st_hash) if e.sha256 else p(tr("rep.error", e=e.error), st_err)
        data.append([p(i, st_cell), p(e.rel_path, st_cell), p(e.created, st_cell),
                     p(fmt_int(e.size), st_num), digest])
    if not result.entries:
        data.append(["", p(tr("rep.empty"), st_cell), "", "", ""])
    table = LongTable(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6FA")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4D6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)

    if result.skipped:
        story.append(Paragraph(tr("rep.skipped"), st_h))
        story.append(kv_table(result.skipped))

    operator = meta["case"].get("operator", "")
    story.append(KeepTogether([
        Paragraph(tr("rep.integrity"), st_h),
        kv_table([
            (tr("rep.txt_file"), os.path.basename(txt_path)),
            (tr("rep.txt_hash"), sha256_file(txt_path)),
        ]),
        Spacer(1, 18 * mm),
        p(tr("rep.signed") + (operator or "_______________________________"), st_v),
    ]))

    _NumberedCanvas.reference = meta["case"].get("reference", "")
    _NumberedCanvas.font = regular
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=15 * mm,
                            title=tr("rep.title"), author=operator, creator=f"{APP_NAME} {__version__}")
    doc.build(story, canvasmaker=_NumberedCanvas)


# --- Orquestación ----------------------------------------------------------------

def safe_name(text):
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in text.strip())
    return keep.strip("_")[:60] or "ref"


def create_reports(root, case, dest_dir, progress=None, cancel=None, include_hidden=True):
    """Escanea `root` y genera PDF + TXT en `dest_dir`. Devuelve (pdf, txt, result)."""
    meta = {
        "case": case,
        "start": format_ts(datetime.now().timestamp()),
        "host": platform.node(),
        "user": getpass.getuser(),
        "volume": volume_info(root),
    }
    result = scan(root, progress, cancel, include_hidden)
    meta["end"] = format_ts(datetime.now().timestamp())

    base = f"{tr('rep.file_prefix')}_{safe_name(case.get('reference', ''))}_{datetime.now():%Y%m%d_%H%M%S}"
    txt = os.path.join(dest_dir, base + ".txt")
    pdf = os.path.join(dest_dir, base + ".pdf")
    write_txt(txt, meta, result)
    write_pdf(pdf, meta, result, txt)
    return pdf, txt, result
