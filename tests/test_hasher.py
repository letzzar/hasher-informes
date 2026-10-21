import ctypes
import hashlib
import os
import re
import sys
import tempfile
import threading
import unittest
from unittest import mock

from hasher import settings
from hasher.core import Cancelled, _long, scan
from hasher.gui import is_inside
from hasher.i18n import set_language
from hasher.report import create_reports

WINDOWS = sys.platform == "win32"


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ScanTests(unittest.TestCase):
    def setUp(self):
        set_language("es")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.files = {
            "b.txt": b"hola",
            "A.txt": b"",
            os.path.join("sub", "año ñ.bin"): os.urandom(3 * 1024 * 1024 + 7),
        }
        for rel, data in self.files.items():
            path = os.path.join(self.root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        os.makedirs(os.path.join(self.root, "vacia"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_hashes_sizes_and_order(self):
        result = scan(self.root)
        got = {e.rel_path: (e.sha256, e.size) for e in result.entries}
        self.assertEqual(got, {rel: (sha(d), len(d)) for rel, d in self.files.items()})
        self.assertEqual([e.rel_path for e in result.entries],
                         ["A.txt", "b.txt", os.path.join("sub", "año ñ.bin")])
        self.assertEqual(result.n_dirs, 2)
        self.assertEqual(result.n_errors, 0)
        self.assertRegex(result.entries[0].created, r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d\d:\d\d|N/D)$")

    def test_dotfiles_excluded(self):
        for rel in (".DS_Store", os.path.join("sub", "._foto.jpg")):
            with open(os.path.join(self.root, rel), "wb") as f:
                f.write(b"mac")
        result = scan(self.root, include_hidden=False)
        self.assertEqual(len(result.entries), len(self.files))
        self.assertEqual(result.hidden_files, 2)
        self.assertEqual(len(scan(self.root, include_hidden=True).entries), len(self.files) + 2)

    def test_english_report(self):
        set_language("en")
        with tempfile.TemporaryDirectory() as out:
            pdf, txt, _ = create_reports(self.root, {"reference": "C-1"}, out)
            with open(txt, encoding="utf-8-sig") as f:
                content = f.read()
        self.assertIn("DIGITAL MEDIA CONTENT REPORT", content)
        self.assertIn("No. | Name | Creation date | Size (bytes) | SHA-256", content)
        self.assertTrue(os.path.basename(pdf).startswith("Report_C-1_"))

    def test_source_not_modified(self):
        before = {rel: os.stat(os.path.join(self.root, rel)).st_mtime_ns for rel in self.files}
        scan(self.root)
        after = {rel: os.stat(os.path.join(self.root, rel)).st_mtime_ns for rel in self.files}
        self.assertEqual(before, after)

    def test_long_path(self):
        deep = _long(self.root)
        for _ in range(12):
            deep = os.path.join(deep, "carpeta_con_nombre_largo_" + "x" * 10)
        os.makedirs(deep)
        with open(os.path.join(deep, "final.txt"), "wb") as f:
            f.write(b"profundo")
        entry = [e for e in scan(self.root).entries if e.rel_path.endswith("final.txt")][0]
        self.assertGreater(len(os.path.join(self.root, entry.rel_path)), 260)
        self.assertEqual(entry.sha256, sha(b"profundo"))

    def test_cancel(self):
        ev = threading.Event()
        ev.set()
        with self.assertRaises(Cancelled):
            scan(self.root, cancel=ev)

    def test_reports(self):
        with tempfile.TemporaryDirectory() as out:
            case = {"reference": "D-123/2026", "operator": "Agente Pérez", "provided_by": "",
                    "media": "Pendrive", "notes": ""}
            pdf, txt, result = create_reports(self.root, case, out)
            self.assertTrue(os.path.getsize(pdf) > 1000)
            with open(txt, encoding="utf-8-sig") as f:
                content = f.read()
            for rel, data in self.files.items():
                self.assertRegex(content, rf"\| {re.escape(rel)} \| [^|]+ \| {len(data)} \| {sha(data)}\r?\n")
            self.assertIn("D-123/2026", content)
            self.assertTrue(os.path.basename(pdf).startswith("Informe_D-123_2026_"))

    def test_empty_source(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as out:
            pdf, _, result = create_reports(src, {"reference": "X"}, out)
            self.assertEqual(result.entries, [])
            self.assertTrue(os.path.exists(pdf))


@unittest.skipUnless(WINDOWS, "atributos oculto/sistema de Windows")
class HiddenTests(unittest.TestCase):
    def setUp(self):
        set_language("es")
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        os.makedirs(os.path.join(r, ".Trashes", "501"))
        os.makedirs(os.path.join(r, "Oculta"))
        os.makedirs(os.path.join(r, "fotos"))
        for rel in (".DS_Store", os.path.join("fotos", "._img.jpg"), os.path.join("fotos", "img.jpg"),
                    os.path.join(".Trashes", "501", "x"), os.path.join("Oculta", "y.txt"),
                    "Thumbs.db", "visible.txt"):
            with open(os.path.join(r, rel), "wb") as f:
                f.write(b"x")
        ctypes.windll.kernel32.SetFileAttributesW(os.path.join(r, "Oculta"), 0x2)  # oculto
        ctypes.windll.kernel32.SetFileAttributesW(os.path.join(r, "Thumbs.db"), 0x2 | 0x4)  # oculto+sistema

    def tearDown(self):
        self.tmp.cleanup()

    def test_excluded(self):
        result = scan(self.tmp.name, include_hidden=False)
        self.assertEqual([e.rel_path for e in result.entries], [os.path.join("fotos", "img.jpg"), "visible.txt"])
        self.assertEqual((result.hidden_files, result.hidden_dirs), (3, 2))  # .DS_Store, ._img.jpg, Thumbs.db
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, ".DS_Store")))  # nada se borra

    def test_included(self):
        result = scan(self.tmp.name, include_hidden=True)
        self.assertEqual(len(result.entries), 7)
        self.assertEqual((result.hidden_files, result.hidden_dirs), (0, 0))

    def test_report_states_exclusion(self):
        with tempfile.TemporaryDirectory() as out:
            _, txt, _ = create_reports(self.tmp.name, {"reference": "X"}, out, include_hidden=False)
            with open(txt, encoding="utf-8-sig") as f:
                content = f.read()
            self.assertIn("Excluidos del informe (3 archivos, 2 carpetas)", content)
            self.assertNotIn(".DS_Store", content)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"APPDATA": self.tmp.name, "XDG_CONFIG_HOME": self.tmp.name, "HOME": self.tmp.name}
        self.patch = mock.patch.dict(os.environ, env)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_defaults_when_missing(self):
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_roundtrip_ignores_case_data(self):
        data = dict(settings.DEFAULTS, language="en", theme="dark", dest="/x", include_hidden=True,
                    reference="NO-GUARDAR")
        settings.save(data)
        self.assertTrue(settings.settings_path().startswith(self.tmp.name))
        loaded = settings.load()
        self.assertEqual((loaded["language"], loaded["theme"], loaded["dest"], loaded["include_hidden"]),
                         ("en", "dark", "/x", True))
        self.assertNotIn("reference", loaded)

    def test_corrupt_file(self):
        os.makedirs(settings.config_dir(), exist_ok=True)
        with open(settings.settings_path(), "w") as f:
            f.write("{no es json")
        self.assertEqual(settings.load(), settings.DEFAULTS)


@unittest.skipUnless(WINDOWS, "rutas de Windows")
class IsInsideTests(unittest.TestCase):
    def test_is_inside(self):
        self.assertTrue(is_inside(r"E:\a\b", "E:\\"))
        self.assertTrue(is_inside(r"C:\x\y", r"c:\X"))
        self.assertFalse(is_inside(r"C:\xy", r"C:\x"))
        self.assertFalse(is_inside(r"D:\x", r"C:\x"))


if __name__ == "__main__":
    unittest.main()
