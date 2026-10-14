#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_v4.py - Palette claire + parsing correct des CTkButton."""
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

PALETTE = {
    "BG":     "#f8f5ed",
    "CARD":   "#fefcf7",
    "BORDER": "#d6d1c4",
    "TEXT":   "#3a3733",
    "MUTED":  "#8a8479",
    "ACCENT": "#4a6b8a",
    "USER":   "#4d6d8a",
}


def log(m=""):
    print(m, flush=True)


def fix_palette(src):
    n = 0
    for key, val in PALETTE.items():
        pat = re.compile(rf'^{key}\s*=\s*["\']#[0-9a-fA-F]{{3,8}}["\']',
                         re.MULTILINE)
        src, k = pat.subn(f'{key} = "{val}"', src)
        n += k
    return src, n


def fix_mode(src):
    if 'set_appearance_mode("dark")' in src:
        return src.replace('set_appearance_mode("dark")',
                           'set_appearance_mode("light")'), 1
    return src, 0


def fix_hover(src):
    n = 0
    for old, new in [
        ('#21262d', '#e8e3d5'),
        ('#79b8ff', '#3a5670'),
        ('#30363d', '#e8e3d5'),
    ]:
        pat = re.compile(rf'hover_color\s*=\s*["\']{re.escape(old)}["\']')
        src, k = pat.subn(f'hover_color="{new}"', src)
        n += k
    return src, n


def find_matching_paren(lines, start_line):
    """Trouve la ligne/col de la parenthese fermante qui matche le premier (
    ouverte a partir de start_line. Retourne (line_idx, col_idx) ou None."""
    depth = 0
    started = False
    for j in range(start_line, len(lines)):
        line = lines[j]
        for k, ch in enumerate(line):
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
                if started and depth == 0:
                    return (j, k)
    return None


def insert_text_color(src):
    """
    Parcourt le fichier, trouve chaque 'CTkButton(' et insere
    'text_color=TEXT' avant la parenthese fermante correspondante.
    Verifie les virgules pour ne pas en mettre en double.
    """
    lines = src.splitlines(keepends=True)
    out = []
    i = 0
    n = 0
    while i < len(lines):
        line = lines[i]
        if "CTkButton(" in line:
            # Verifier si text_color est deja present dans le bloc
            close = find_matching_paren(lines, i)
            if close is None:
                out.append(line)
                i += 1
                continue
            end_line, end_col = close
            block = "".join(lines[i:end_line + 1])
            if "text_color" in block:
                # Deja patche. On avance jusqu'a la fin du bloc.
                out.extend(lines[i:end_line + 1])
                i = end_line + 1
                continue
            # Inserer ', text_color=TEXT' avant la ) fermante
            target_line = lines[end_line]
            before = target_line[:end_col]
            after = target_line[end_col:]
            before_rstripped = before.rstrip()
            if before_rstripped.endswith("("):
                # Juste "(" : pas de virgule
                new_line = before_rstripped + "text_color=TEXT" + after
            elif before_rstripped.endswith(","):
                # Virgule deja presente : ajouter juste l'argument
                new_line = before_rstripped + " text_color=TEXT" + after
            else:
                # Ajouter ", text_color=TEXT"
                new_line = before_rstripped + ", text_color=TEXT" + after
            lines[end_line] = new_line
            n += 1
            out.extend(lines[i:end_line + 1])
            i = end_line + 1
        else:
            out.append(line)
            i += 1
    return "".join(out), n


def main():
    log("=" * 72)
    log("FIX V4 - palette claire + parsing correct des CTkButton")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # [1] Palette
    log("[1/4] Palette...")
    src, n = fix_palette(src)
    log(f"  -> {n} constante(s)")

    # [2] Mode
    log("[2/4] Mode light...")
    src, n = fix_mode(src)
    log(f"  -> {n} set_appearance_mode")

    # [3] Hover
    log("[3/4] Hover...")
    src, n = fix_hover(src)
    log(f"  -> {n} hover_color")

    # [4] text_color sur CTkButton (parsing propre)
    log("[4/4] text_color sur CTkButton...")
    src, n = insert_text_color(src)
    log(f"  -> {n} bouton(s)")

    # Verif syntaxe
    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Restaure.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Verification des valeurs apres :")
    src2 = TARGET.read_text(encoding="utf-8")
    for key in PALETTE:
        m = re.search(rf'^{key}\s*=\s*["\']([^"\']+)["\']', src2, re.MULTILINE)
        if m:
            log(f"  {key:8s} = {m.group(1)}")
    n_tc = len(re.findall(r"text_color=TEXT", src2))
    log(f"  text_color=TEXT : {n_tc} occurrence(s)")
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())