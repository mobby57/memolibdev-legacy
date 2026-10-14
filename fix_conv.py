#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_conv.py - Reset conversation au changement de projet."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "self._v2_assistant.new_conversation()" in src:
    print("Deja patche.")
    raise SystemExit(0)

OLD = """            self._v2_assistant = AssistantV2(
                project_root.resolve(),
                index=self._v2_index,
            )
"""

NEW = """            self._v2_assistant = AssistantV2(
                project_root.resolve(),
                index=self._v2_index,
            )
            try:
                self._v2_assistant.new_conversation()
                self._system("Nouvelle conversation V2")
            except Exception:
                pass
"""

if OLD not in src:
    print("ERREUR : bloc AssistantV2 introuvable")
    print("Cherche :", repr(OLD[:60]))
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
print(f"OK - patch applique (backup : {BK.name}/)")
print()
print("Relancez : python .\\memolibdev_gui_v4.py")