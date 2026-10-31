#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_v5.py - Cherche le dernier caractere non-blanc avant la ) fermante."""
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


def insert_text_color(full: str) -> tuple[str, int]:
    """
    Parcourt full (string) a la recherche de 'CTkButton('.
    Pour chaque, trouve la ) fermante par balancement de parentheses.
    Cherche le dernier caractere NON-BLANC avant cette ). Insere
    ', text_color=TEXT' ou ' text_color=TEXT' selon ce caractere.
    """
    result = []
    pos = 0
    n = 0
    while True:
        idx = full.find("CTkButton(", pos)
        if idx == -1:
            result.append(full[pos:])
            break
        result.append(full[pos:idx])

        # Trouver le '(' de CTkButton
        open_idx = idx + len("CTkButton")
        while open_idx < len(full) and full[open_idx] != "(":
            open_idx += 1

        # Balancement de parentheses
        depth = 0
        started = False
        close_idx = None
        for j in range(open_idx, len(full)):
            ch = full[j]
            if ch == "(":
                depth += 1
                started = True
            elif ch == ")":
                depth -= 1
                if started and depth == 0:
                    close_idx = j
                    break

        if close_idx is None:
            result.append(full[idx:])
            break

        block = full[idx:close_idx + 1]
        if "text_color" in block:
            result.append(block)
            pos = close_idx + 1
            continue

        # Chercher le dernier caractere non-blanc AVANT close_idx
        k = close_idx - 1
        while k > open_idx and full[k] in " \t\n\r":
            k -= 1
        # full[k] est le dernier char non-blanc
        last_char = full[k] if k >= open_idx else "("

        if last_char == "(":
            insert_text = "text_color=TEXT"
        elif last_char == ",":
            insert_text = " text_color=TEXT"
        else:
            insert_text = ", text_color=TEXT"

        # Insertion apres k
        insert_pos = k + 1
        result.append(full[idx:insert_pos])
        result.append(insert_text)
        result.append(full[insert_pos:close_idx + 1])
        pos = close_idx + 1
        n += 1

    return "".join(result), n


def main():
    log("=" * 72)
    log("FIX V5 - parsing correct des parentheses")
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

    log("[1/4] Palette...")
    src, n = fix_palette(src)
    log(f"  -> {n} constante(s)")

    log("[2/4] Mode light...")
    src, n = fix_mode(src)
    log(f"  -> {n} set_appearance_mode")

    log("[3/4] Hover...")
    src, n = fix_hover(src)
    log(f"  -> {n} hover_color")

    log("[4/4] text_color sur CTkButton...")
    src, n = insert_text_color(src)
    log(f"  -> {n} bouton(s)")

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
    log("Verification apres :")
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