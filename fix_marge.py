#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_marge.py - Ajoute une marge au-dessus du chat."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if 'self.chat.grid(row=1, column=1, sticky="nsew", pady=(8, 0))' in src:
    print("Deja patche.")
    raise SystemExit(0)

OLD = 'self.chat.grid(row=1, column=1, sticky="nsew")'
NEW = 'self.chat.grid(row=1, column=1, sticky="nsew", pady=(8, 0))'

if OLD not in src:
    print("ERREUR : ligne introuvable.")
    print("Cherche :", OLD)
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
print(f"OK - marge chat appliquee")
print(f"Backup : {BK.name}/")