#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_final.py - Patch complet : palette + mode + text_color + hover."""
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
HOVER_LIGHT = "#e8e3d5"
HOVER_ACCENT_LIGHT = "#3a5670"  # pour hover sur bouton ACCENT


def log(m=""):
    print(m, flush=True)


def fix_palette(src):
    n = 0
    for key, val in PALETTE.items():
        pattern = re.compile(
            rf'^{key}\s*=\s*["\']#[0-9a-fA-F]{{3,8}}["\']',
            re.MULTILINE,
        )
        new_src, k = pattern.subn(f'{key} = "{val}"', src)
        if k:
            n += k
        src = new_src
    return src, n


def fix_mode(src):
    if 'set_appearance_mode("dark")' in src:
        return src.replace('set_appearance_mode("dark")',
                           'set_appearance_mode("light")'), 1
    return src, 0


def fix_hover(src):
    n = 0
    src, k = re.subn(r'hover_color\s*=\s*["\']#21262d["\']',
                     f'hover_color="{HOVER_LIGHT}"', src)
    n += k
    src, k = re.subn(r'hover_color\s*=\s*["\']#79b8ff["\']',
                     f'hover_color="{HOVER_ACCENT_LIGHT}"', src)
    n += k
    src, k = re.subn(r'hover_color\s*=\s*["\']#30363d["\']',
                     f'hover_color="{HOVER_LIGHT}"', src)
    n += k
    return src, n


def fix_text_color_in_buttons(src):
    """
    Insere text_color=TEXT DANS l'appel CTkButton.
    On parcourt ligne par ligne, on detecte 'CTkButton(' et on trouve
    la parenthese fermante correspondante. On insere ', text_color=TEXT'
    juste avant.
    """
    lines = src.splitlines(keepends=True)
    out_lines = []
    i = 0
    n = 0
    while i < len(lines):
        line = lines[i]
        # Detecte un appel CTkButton sur cette ligne
        if "CTkButton(" in line:
            # Compte les parentheses ouvrantes sur cette ligne
            block_start = i
            depth = 0
            block_end = i
            # Cherche la fin de l'appel
            for j in range(i, min(len(lines), i + 40)):
                depth += lines[j].count("(") - lines[j].count(")")
                if depth <= 0 and "(" in "".join(lines[i:j+1]):
                    block_end = j
                    break
            # Verifie si text_color est deja present dans le bloc
            block = lines[block_start:block_end + 1]
            block_str = "".join(block)
            if "text_color" not in block_str:
                # Insere ', text_color=TEXT' avant la derniere )
                # On cherche la ligne avec la ) fermante
                for k in range(block_end, block_start - 1, -1):
                    lk = lines[k]
                    # Cas : la ligne se termine par ")  (eventuellement suivie de .grid/.pack)
                    m = re.match(r'^(.*?)(\)(\s*\.\s*\w+\([^\n]*)?\s*)$', lk)
                    if m and ")" in lk:
                        # Insere ", text_color=TEXT" avant la premiere )
                        new_lk = lk.replace(")", ", text_color=TEXT)", 1)
                        lines[k] = new_lk
                        n += 1
                        break
            i = block_end + 1
            out_lines.extend(lines[block_start:block_end + 1])
        else:
            out_lines.append(line)
            i += 1
    return "".join(out_lines), n


def main():
    log("=" * 72)
    log("FIX FINAL - palette claire + mode + text_color + hover")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log(f"ERREUR : {TARGET.name} introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # [1] Palette
    log("[1/4] Palette Confort Visuel...")
    src, n = fix_palette(src)
    log(f"  -> {n} constante(s) remplacee(s)")
    for k, v in PALETTE.items():
        log(f"     {k} = {v}")

    # [2] Mode light
    log("[2/4] Mode CustomTkinter...")
    src, n = fix_mode(src)
    log(f"  -> {n} set_appearance_mode change(s)")

    # [3] Hover
    log("[3/4] Hover colors...")
    src, n = fix_hover(src)
    log(f"  -> {n} hover_color remplace(s)")

    # [4] text_color dans CTkButton
    log("[4/4] text_color=TEXT dans les CTkButton...")
    src, n = fix_text_color_in_buttons(src)
    log(f"  -> {n} bouton(s) patche(s)")

    # Verif syntaxe
    log()
    log("Verification syntaxique...")
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
    log("Verification des valeurs apres patch :")
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