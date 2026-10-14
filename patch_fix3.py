#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_fix3.py - Rollback + theme clair + text_color correct."""
from __future__ import annotations
import ast
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


PALETTE = {
    "BG":     "#f8f5ed",
    "CARD":   "#fefcf7",
    "ACCENT": "#4a6b8a",
    "TEXT":   "#3a3733",
    "MUTED":  "#8a8479",
    "USER":   "#4d6d8a",
    "BORDER": "#d6d1c4",
}


def main():
    log("=" * 72)
    log("PATCH FIX3 - rollback + theme clair + text_color correct")
    log("=" * 72)
    log()

    # [0] ROLLBACK via git
    log("[0/5] Rollback via git...")
    r = subprocess.run(
        ["git", "checkout", "--", TARGET.name],
        cwd=ROOT, capture_output=True, text=True,
    )
    if r.returncode != 0:
        log(f"  ATTENTION git checkout : {r.stderr.strip()}")
        log("  On continue avec l'etat actuel.")
    else:
        log("  -> memolibdev_gui_v4.py restaure depuis HEAD")

    src = TARGET.read_text(encoding="utf-8")

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"  backup -> {BK.name}/{TARGET.name}")
    log()

    # [1] Palette claire
    log("[1/5] Application palette Confort Visuel...")
    pattern = re.compile(
        r'^(BG|CARD|ACCENT|TEXT|MUTED|USER|BORDER)\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']',
        re.MULTILINE,
    )
    def repl(m):
        key = m.group(1)
        return f'{key} = "{PALETTE.get(key, m.group(0).split(chr(34))[1])}"'
    src = pattern.sub(repl, src)
    # S'assurer que BORDER existe
    if "BORDER = " not in src:
        # Injecter apres USER
        src = re.sub(r'(USER\s*=\s*"[^"]+"\n)',
                     r'\1BORDER = "#d6d1c4"\n', src, count=1)
    log("  -> palette appliquee")

    # [2] set_appearance_mode light
    log("[2/5] Mode CustomTkinter light...")
    if 'set_appearance_mode("dark")' in src:
        src = src.replace('set_appearance_mode("dark")',
                          'set_appearance_mode("light")')
        log("  -> dark -> light")
    elif 'set_appearance_mode("light")' in src:
        log("  -> deja light")
    elif "set_appearance_mode" not in src:
        lines = src.splitlines(keepends=True)
        for i, l in enumerate(lines):
            if "import customtkinter" in l:
                lines.insert(i + 1, 'ctk.set_appearance_mode("light")\n')
                break
        src = "".join(lines)
        log("  -> light ajoute par defaut")

    # [3] Hover sombre -> clair
    log("[3/5] hover_color clair...")
    src, n_hover = re.subn(
        r'hover_color\s*=\s*["\']#21262d["\']',
        'hover_color="#e8e3d5"',
        src,
    )
    log(f"  -> {n_hover} hover_color remplaces")

    # [4] text_color=TEXT DANS CTkButton
    #     On remplace `border_color=BORDER)` par
    #     `border_color=BORDER, text_color=TEXT)`
    #     AVANT le `.grid(` ou `.pack(` qui suit
    log("[4/5] Insertion text_color=TEXT dans CTkButton...")

    # Pattern : on cible uniquement les fermetures de CTkButton
    # qui se terminent par `border_color=BORDER)` suivi de `.grid(` ou `.pack(`
    def add_text_color(m):
        return m.group(1) + ', text_color=TEXT' + m.group(2)
    
    # Cas A : border_color=BORDER)  suivi de .grid ou .pack
    src, n_a = re.subn(
        r'(border_color=BORDER)(\)\s*\.\s*(?:grid|pack)\()',
        lambda m: m.group(1) + ', text_color=TEXT' + m.group(2),
        src,
    )
    log(f"  -> {n_a} bouton(s) avec border_color=BORDER patche(s)")

    # Cas B : hover_color=...)  suivi de .grid ou .pack  (sans border)
    src, n_b = re.subn(
        r'(hover_color=#[0-9a-fA-F]{3,8})(\)\s*\.\s*(?:grid|pack)\()',
        lambda m: m.group(1) + ', text_color=TEXT' + m.group(2),
        src,
    )
    log(f"  -> {n_b} bouton(s) avec hover_color patche(s)")

    # [5] Verif syntaxe
    log("[5/5] Verification syntaxique...")
    try:
        ast.parse(src)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        log(f"  Restauration...")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Fichier restaure.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())