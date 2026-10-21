"""Interfaz gráfica (Tkinter + sv-ttk). El escaneo corre en un hilo y se comunica por cola."""
import ctypes
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

import darkdetect
import sv_ttk

from . import APP_NAME, REPO_URL, __version__, settings
from .core import Cancelled, list_drives
from .i18n import LANGUAGES, set_language, tr
from .report import create_reports, human_size

CASE_FIELDS = ["reference", "operator", "provided_by", "media"]
PALETTE = {  # colores que sv-ttk no gestiona (tk.Text y textos secundarios)
    "light": {"text_bg": "#fdfdfd", "text_fg": "#1c1c1c", "border": "#c8c8c8", "sub": "#5c5c5c"},
    "dark": {"text_bg": "#2b2b2b", "text_fg": "#fafafa", "border": "#4a4a4a", "sub": "#a8a8a8"},
}


def resource_path(*parts):
    """Ruta a un recurso, tanto en desarrollo como dentro del ejecutable de PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def open_path(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", path])


def is_inside(child, parent):
    """True si `child` es `parent` o está dentro de él."""
    c = os.path.normcase(os.path.realpath(child))
    p = os.path.normcase(os.path.realpath(parent))
    try:
        return os.path.commonpath([c, p]) == p
    except ValueError:  # unidades distintas
        return False


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = settings.load()
        set_language(self.cfg["language"])
        self.minsize(720, 680)
        if self.cfg["geometry"]:
            self.geometry(self.cfg["geometry"])
        self.queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.last_pdf = None

        self.icon = tk.PhotoImage(file=resource_path("assets", "icono.png"))
        self.iconphoto(True, self.icon)

        self.source = tk.StringVar(value=self.cfg["source"])
        self.dest = tk.StringVar(value=self.cfg["dest"] or os.path.join(os.path.expanduser("~"), "Documents"))
        self.case = {key: tk.StringVar() for key in CASE_FIELDS}
        self.case["operator"].set(self.cfg["operator"])
        self.include_hidden = tk.BooleanVar(value=self.cfg["include_hidden"])
        self.status = tk.StringVar()
        self.current = tk.StringVar()
        self.language = tk.StringVar(value=self.cfg["language"])
        self.theme = tk.StringVar(value=self.cfg["theme"] or ("dark" if darkdetect.isDark() else "light"))

        self.main = None
        self._build()
        self.apply_theme()
        self.refresh_drives()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- construcción de la ventana -------------------------------------------

    def _build(self, notes=""):
        self.title(f"{APP_NAME} {__version__} — {tr('app.subtitle')}")
        self.main = ttk.Frame(self)
        self.main.pack(fill="both", expand=True)
        self._build_menu()
        root = ttk.Frame(self.main, padding=(16, 8, 16, 16))
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)

        head = ttk.Frame(root)
        head.grid(sticky="ew", pady=(0, 10))
        self.logo = self.icon.subsample(4)  # 64 px
        ttk.Label(head, image=self.logo).pack(side="left", padx=(0, 12))
        txt = ttk.Frame(head)
        txt.pack(side="left", fill="x", expand=True)
        ttk.Label(txt, text=tr("ui.title"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(txt, text=tr("ui.lead"), style="Sub.TLabel", wraplength=560).pack(anchor="w")

        # 1. Origen
        f1 = ttk.LabelFrame(root, text=tr("ui.source"), padding=10)
        f1.grid(sticky="ew", pady=4)
        f1.columnconfigure(1, weight=1)
        ttk.Label(f1, text=tr("ui.drive")).grid(row=0, column=0, sticky="w")
        self.drive_combo = ttk.Combobox(f1, state="readonly")
        self.drive_combo.grid(row=0, column=1, sticky="ew", padx=6)
        self.drive_combo.bind("<<ComboboxSelected>>", self.on_drive)
        ttk.Button(f1, text=tr("ui.refresh"), command=self.refresh_drives).grid(row=0, column=2, sticky="ew")
        ttk.Label(f1, text=tr("ui.path")).grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(f1, textvariable=self.source).grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(f1, text=tr("ui.folder"), command=self.pick_source).grid(row=1, column=2, pady=(6, 0), sticky="ew")
        ttk.Checkbutton(f1, variable=self.include_hidden, text=tr("ui.hidden")
                        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=6, pady=(8, 0))

        # 2. Datos del caso
        f2 = ttk.LabelFrame(root, text=tr("ui.case"), padding=10)
        f2.grid(sticky="ew", pady=4)
        f2.columnconfigure(1, weight=1)
        for i, key in enumerate(CASE_FIELDS):
            ttk.Label(f2, text=tr(f"ui.{key}") + ":").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(f2, textvariable=self.case[key]).grid(row=i, column=1, sticky="ew", padx=6, pady=2)
        ttk.Label(f2, text=tr("ui.notes") + ":").grid(row=len(CASE_FIELDS), column=0, sticky="nw", pady=2)
        self.notes = tk.Text(f2, height=3, wrap="word", relief="flat", borderwidth=0,
                             highlightthickness=1, padx=6, pady=4)
        self.notes.grid(row=len(CASE_FIELDS), column=1, sticky="ew", padx=6, pady=2)
        self.notes.insert("1.0", notes)

        # 3. Destino
        f3 = ttk.LabelFrame(root, text=tr("ui.dest"), padding=10)
        f3.grid(sticky="ew", pady=4)
        f3.columnconfigure(0, weight=1)
        ttk.Entry(f3, textvariable=self.dest).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(f3, text=tr("ui.browse"), command=self.pick_dest).grid(row=0, column=1)

        # Progreso
        f4 = ttk.Frame(root)
        f4.grid(sticky="ew", pady=(12, 4))
        f4.columnconfigure(0, weight=1)
        self.bar = ttk.Progressbar(f4, maximum=1000)
        self.bar.grid(sticky="ew")
        ttk.Label(f4, textvariable=self.status).grid(sticky="w", pady=(4, 0))
        ttk.Label(f4, textvariable=self.current, style="Sub.TLabel").grid(sticky="w")
        self.status.set(tr("ui.ready"))

        # Botones
        f5 = ttk.Frame(root)
        f5.grid(sticky="ew", pady=(8, 0))
        self.btn_run = ttk.Button(f5, text=tr("ui.run"), style="Accent.TButton", command=self.start)
        self.btn_run.pack(side="left", ipadx=8, ipady=2)
        self.btn_cancel = ttk.Button(f5, text=tr("ui.cancel"), command=self.cancel.set, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.btn_folder = ttk.Button(f5, text=tr("ui.open_folder"), command=self.open_folder, state="disabled")
        self.btn_folder.pack(side="right")
        self.btn_pdf = ttk.Button(f5, text=tr("ui.open_pdf"), command=self.open_pdf, state="disabled")
        self.btn_pdf.pack(side="right", padx=8)

        self.inputs = [w for f in (f1, f2, f3) for w in f.winfo_children()
                       if isinstance(w, (ttk.Entry, ttk.Button, ttk.Combobox, ttk.Checkbutton, tk.Text))]

    def _build_menu(self):
        """Menús Ver y Ayuda: barra nativa en macOS; en Windows/Linux, botones con el estilo
        del tema (la barra nativa de Windows no admite modo oscuro)."""
        native = sys.platform == "darwin"
        if native:
            bar = tk.Menu(self)
        else:
            bar = ttk.Frame(self.main, padding=(8, 4, 8, 0))
            bar.pack(fill="x")

        def submenu(label):
            if native:
                menu = tk.Menu(bar, tearoff=False)
                bar.add_cascade(label=label, menu=menu)
            else:
                button = ttk.Menubutton(bar, text=label, style="Toolbutton")
                button.pack(side="left")
                menu = tk.Menu(button, tearoff=False)
                button["menu"] = menu
            return menu

        view = submenu(tr("menu.view"))
        theme = tk.Menu(view, tearoff=False)
        for value, key in (("light", "menu.light"), ("dark", "menu.dark")):
            theme.add_radiobutton(label=tr(key), value=value, variable=self.theme, command=self.apply_theme)
        view.add_cascade(label=tr("menu.theme"), menu=theme)
        lang = tk.Menu(view, tearoff=False)
        for code, name in LANGUAGES.items():
            lang.add_radiobutton(label=name, value=code, variable=self.language, command=self.change_language)
        view.add_cascade(label=tr("menu.language"), menu=lang)
        help_menu = submenu(tr("menu.help"))
        help_menu.add_command(label=tr("menu.about"), command=self.show_about)
        if native:
            self.config(menu=bar)

    # --- tema e idioma ----------------------------------------------------------

    def apply_theme(self):
        mode = self.theme.get()
        sv_ttk.set_theme(mode)
        pal = PALETTE[mode]
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("Sub.TLabel", foreground=pal["sub"])
        self.notes.configure(bg=pal["text_bg"], fg=pal["text_fg"], insertbackground=pal["text_fg"],
                             highlightbackground=pal["border"], highlightcolor=pal["border"],
                             font=("Segoe UI", 10))
        if sys.platform == "win32":
            self._dark_titlebar(self, mode == "dark")
            self.after(100, self._dark_titlebar, self, mode == "dark")  # al arrancar la ventana aún no existe

    @staticmethod
    def _dark_titlebar(win, dark):
        """Barra de título oscura/clara en Windows 10/11."""
        try:
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)  # repintar el marco
        except (AttributeError, OSError, tk.TclError):
            pass

    def change_language(self):
        if self.worker and self.worker.is_alive():
            self.language.set(self.cfg["language"])  # no se cambia durante un análisis
            return
        self.cfg["language"] = self.language.get()
        set_language(self.cfg["language"])
        notes = self.notes.get("1.0", "end").rstrip("\n")
        self.main.destroy()
        self._build(notes)
        self.apply_theme()
        self.refresh_drives()
        if self.last_pdf:
            self.btn_pdf.state(["!disabled"])
            self.btn_folder.state(["!disabled"])

    def show_about(self):
        win = tk.Toplevel(self)
        win.title(tr("about.title"))
        win.resizable(False, False)
        win.transient(self)
        frame = ttk.Frame(win, padding=24)
        frame.pack(fill="both", expand=True)
        self.about_logo = self.icon.subsample(2)  # 128 px
        ttk.Label(frame, image=self.about_logo).pack()
        ttk.Label(frame, text=APP_NAME, font=("Segoe UI Semibold", 15)).pack(pady=(8, 0))
        ttk.Label(frame, text=tr("about.version", v=__version__), style="Sub.TLabel").pack()
        ttk.Label(frame, text=tr("about.body"), wraplength=340, justify="center").pack(pady=12)
        link = ttk.Label(frame, text=REPO_URL.removeprefix("https://"), foreground="#4a90d9", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda _e: webbrowser.open(REPO_URL))
        ttk.Label(frame, text=tr("about.license"), style="Sub.TLabel").pack(pady=(2, 0))
        ttk.Separator(frame).pack(fill="x", pady=12)
        sign = ttk.Frame(frame)
        sign.pack()
        ttk.Label(sign, text="By Victor ", foreground="#888888").pack(side="left")
        ttk.Label(sign, text="«Letzzar»", foreground="#4a90d9",
                  font=("Segoe UI", 10, "bold italic")).pack(side="left")
        ttk.Label(sign, text=" Gallego", foreground="#888888").pack(side="left")
        ttk.Button(frame, text=tr("about.close"), command=win.destroy).pack(pady=(16, 0))
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")
        if sys.platform == "win32":
            win.after(50, self._dark_titlebar, win, self.theme.get() == "dark")
        win.grab_set()

    # --- acciones ---------------------------------------------------------------

    def refresh_drives(self):
        self.drives = list_drives()
        self.drive_combo["values"] = [text for _, text in self.drives]
        self.drive_combo.set("")

    def on_drive(self, _event):
        self.source.set(self.drives[self.drive_combo.current()][0])

    def pick_source(self):
        path = filedialog.askdirectory(title=tr("ui.pick_source"))
        if path:
            self.source.set(os.path.normpath(path))
            self.drive_combo.set("")

    def pick_dest(self):
        path = filedialog.askdirectory(title=tr("ui.pick_dest"))
        if path:
            self.dest.set(os.path.normpath(path))

    def validate(self):
        src, dest = self.source.get().strip(), self.dest.get().strip()
        if not src or not os.path.isdir(src):
            return tr("err.no_source")
        if not self.case["reference"].get().strip():
            return tr("err.no_reference")
        if not dest or not os.path.isdir(dest):
            return tr("err.no_dest")
        if is_inside(dest, src):
            return tr("err.dest_inside")
        return None

    def start(self):
        error = self.validate()
        if error:
            messagebox.showwarning(APP_NAME, error, parent=self)
            return
        case = {k: v.get().strip() for k, v in self.case.items()}
        case["notes"] = self.notes.get("1.0", "end").strip()
        self.save_settings()
        self.cancel.clear()
        self.last_pdf = None
        self._set_running(True)
        self.status.set(tr("ui.listing"))
        self.worker = threading.Thread(
            target=self._work, args=(self.source.get().strip(), case, self.dest.get().strip(),
                                     self.include_hidden.get()), daemon=True)
        self.worker.start()
        self.after(100, self.poll)

    def _work(self, src, case, dest, include_hidden):
        def progress(*args):
            self.queue.put(("progress", args))
        try:
            pdf, txt, result = create_reports(src, case, dest, progress, self.cancel, include_hidden)
            self.queue.put(("done", (pdf, txt, result)))
        except Cancelled:
            self.queue.put(("cancelled", None))
        except Exception as exc:  # cualquier fallo se muestra al usuario
            self.queue.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll(self):
        last = None
        try:
            while True:
                last = self.queue.get_nowait()
                if last[0] != "progress":
                    break
        except queue.Empty:
            pass
        if last is None:
            self.after(100, self.poll)
            return
        kind, data = last
        if kind == "progress":
            done_f, total_f, done_b, total_b, current = data
            self.bar["value"] = 1000 * done_b / total_b if total_b else 0
            self.status.set(tr("ui.progress", i=min(done_f + 1, total_f), n=total_f,
                               done=human_size(done_b), total=human_size(total_b)))
            self.current.set(current if len(current) < 90 else "…" + current[-89:])
            self.after(100, self.poll)
            return
        self._set_running(False)
        self.current.set("")
        if kind == "done":
            pdf, txt, result = data
            self.last_pdf = pdf
            self.bar["value"] = 1000
            self.status.set(tr("ui.done", name=os.path.basename(pdf)))
            self.btn_pdf.state(["!disabled"])
            self.btn_folder.state(["!disabled"])
            msg = tr("msg.done", files=len(result.entries), size=human_size(result.total_bytes),
                     errors=result.n_errors, pdf=pdf, txt=txt)
            (messagebox.showwarning if result.n_errors else messagebox.showinfo)(APP_NAME, msg, parent=self)
        elif kind == "cancelled":
            self.bar["value"] = 0
            self.status.set(tr("ui.cancelled"))
        else:
            self.bar["value"] = 0
            self.status.set(tr("ui.failed"))
            messagebox.showerror(APP_NAME, tr("err.generic", error=data), parent=self)

    def _set_running(self, running):
        for w in self.inputs:
            if isinstance(w, tk.Text):
                w.configure(state="disabled" if running else "normal")
            elif isinstance(w, ttk.Combobox):
                w.state(["disabled"] if running else ["!disabled", "readonly"])
            else:
                w.state(["disabled"] if running else ["!disabled"])
        self.btn_run.state(["disabled"] if running else ["!disabled"])
        self.btn_cancel.state(["!disabled"] if running else ["disabled"])
        if running:
            self.btn_pdf.state(["disabled"])
            self.btn_folder.state(["disabled"])

    def open_pdf(self):
        if self.last_pdf:
            open_path(self.last_pdf)

    def open_folder(self):
        if self.last_pdf:
            open_path(os.path.dirname(self.last_pdf))

    def save_settings(self):
        self.cfg.update(
            language=self.language.get(), theme=self.theme.get(), source=self.source.get().strip(),
            dest=self.dest.get().strip(), operator=self.case["operator"].get().strip(),
            include_hidden=self.include_hidden.get(), geometry=self.geometry(),
        )
        settings.save(self.cfg)

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, tr("msg.quit_running"), parent=self):
                return
            self.cancel.set()
        self.save_settings()
        self.destroy()


def run():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # texto nítido en pantallas HiDPI
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("letzzar.HasherInformes")
        except (AttributeError, OSError):
            pass
    App().mainloop()
