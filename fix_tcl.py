#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_tcl.py - Protege progress_lbl contre TclError."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "def _update_progress" in src:
    print("Deja patche.")
    raise SystemExit(0)

OLD = '''            if not self._stream_started:
                self._stream_started = True
                self.after(0, lambda: progress_lbl.configure(text="Redaction..."))
                self.after(0, lambda: self._update_spinner("Redaction de la reponse..."))'''

NEW = '''            if not self._stream_started:
                self._stream_started = True
                def _update_progress(lbl=progress_lbl):
                    try:
                        if lbl.winfo_exists():
                            lbl.configure(text="Redaction...")
                    except Exception:
                        pass
                self.after(0, _update_progress)
                self.after(0, lambda: self._update_spinner("Redaction de la reponse..."))'''

if OLD not in src:
    print("ERREUR : bloc introuvable.")
    print("Cherche :", OLD[:80])
    raise SystemExit(1)

src2 = src.replace(OLD, NEW, 1)

try:
    ast.parse(src2)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src2, encoding="utf-8")
print(f"OK - patch TclError applique")
print(f"Backup : {BK.name}/")