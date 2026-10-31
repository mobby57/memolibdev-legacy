#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""force_v2_routing2.py - Force le routage V2 (indentation correcte)."""
from __future__ import annotations
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


# Bloc V2 SANS indentation de base (les lignes relatives ont leur propre niveau)
V2_ROUTING_BASE = [
    "# --- V2 : priorite si disponible ---",
    'if getattr(self, "_v2_ready", False):',
    '    self.entry.delete("1.0", "end")',
    "    if self.v2_chat(text):",
    "        return",
    "# --- sinon, continuer avec la CLI existante ---",
]


def main():
    log("=" * 72)
    log("FORCE V2 ROUTING (v2 - indentation corrigee)")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    # Verif si deja route
    if "if self.v2_chat(text)" in src:
        log("V2 est deja route. Rien a faire.")
        return 0

    # Backup
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # Trouver _on_send
    lines = src.splitlines(keepends=True)
    idx_on_send = None
    for i, l in enumerate(lines):
        if re.match(r"(\s+)def _on_send\(self\):", l):
            idx_on_send = i
            break

    if idx_on_send is None:
        log("ERREUR : _on_send introuvable.")
        return 1

    # Indentation de _on_send (le "def")
    def_line = lines[idx_on_send]
    def_indent = def_line[: len(def_line) - len(def_line.lstrip())]
    # Corps = def_indent + 4 espaces
    body_indent = def_indent + "    "

    # Trouver l'ancre : la ligne "if getattr(self, '_identity_check_pending', False):"
    # dans les 20 lignes apres _on_send
    anchor_idx = None
    for i in range(idx_on_send + 1, min(len(lines), idx_on_send + 25)):
        if "_identity_check_pending" in lines[i]:
            anchor_idx = i
            break

    if anchor_idx is None:
        log("ERREUR : ancre '_identity_check_pending' introuvable.")
        return 1

    # Trouver la fin du bloc if (les lignes qui suivent, plus indentees)
    anchor_line = lines[anchor_idx]
    anchor_indent_len = len(anchor_line) - len(anchor_line.lstrip())

    insert_at = anchor_idx + 1
    # Avancer tant que les lignes sont plus indentees ou vides
    while insert_at < len(lines):
        l = lines[insert_at]
        if not l.strip():
            insert_at += 1
            continue
        cur_indent_len = len(l) - len(l.lstrip())
        if cur_indent_len > anchor_indent_len:
            insert_at += 1
        else:
            break

    log(f"  _on_send ligne {idx_on_send + 1}")
    log(f"  ancre ligne {anchor_idx + 1}")
    log(f"  insertion apres ligne {insert_at}")
    log()

    # Construire le bloc a inserer avec body_indent
    block = "\n"
    for line in V2_ROUTING_BASE:
        if line.startswith("#"):
            block += body_indent + line + "\n"
        else:
            # Ligne avec indentation relative a l'interieur du bloc
            block += body_indent + line + "\n"
    block += "\n"

    # Insertion
    lines.insert(insert_at, block)
    src2 = "".join(lines)

    # Verif syntaxe
    try:
        ast.parse(src2)
        log("Syntaxe OK.")
    except SyntaxError as e:
        log(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        log(f"  >>> {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("Restaure depuis backup.")
        return 1

    TARGET.write_text(src2, encoding="utf-8")

    log()
    log("=" * 72)
    log("ROUTAGE V2 AJOUTE")
    log("=" * 72)
    log()
    log("Verification rapide :")
    log("  Select-String -Path .\\memolibdev_gui_v4.py -Pattern 'v2_chat'")

    # Afficher le bloc insere
    log()
    log("Bloc insere :")
    for l in block.splitlines():
        log("  " + l)

    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())