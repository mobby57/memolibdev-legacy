#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_confort.py - Theme optimal pour les yeux."""
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


NEW_MENU = '''        try:
            ctk.CTkOptionMenu(
                header,
                values=self._available_models or [DEFAULT_MODEL],
                variable=self.model_var,
                width=150,
                height=28,
                font=ctk.CTkFont(size=10),
                dropdown_font=ctk.CTkFont(size=10),
            ).pack(side="right", padx=(4, 8))
        except Exception:
            pass
'''


# --- PALETTE CONFORT VISUEL -------------------------------------------
CONFORT = {
    "BG":     "#f8f5ed",   # creme tres doux
    "CARD":   "#fefcf7",   # blanc casse
    "ACCENT": "#4a6b8a",   # bleu ardoise
    "TEXT":   "#3a3733",   # gris-brun fonce
    "MUTED":  "#8a8479",   # gris chaud
    "USER":   "#4d6d8a",   # bleu ardoise fonce
}


def find_menu_block(lines):
    start = None
    for i, l in enumerate(lines):
        if "CTkOptionMenu" in l:
            for j in range(i, max(0, i - 10), -1):
                if lines[j].strip() == "try:":
                    start = j
                    break
            break
    if start is None:
        return None
    end = start
    for i in range(start, min(len(lines), start + 25)):
        if lines[i].strip() == "pass" and "except" in lines[i - 1]:
            end = i + 1
            break
    return (start, end)


def replace_menu(lines):
    rng = find_menu_block(lines)
    if rng is None:
        return None, "menu introuvable"
    start, end = rng
    new_lines = NEW_MENU.splitlines(keepends=True)
    return lines[:start] + new_lines + lines[end:], "menu compact"


def patch_theme(lines):
    pattern = re.compile(
        r'^(BG|CARD|ACCENT|TEXT|MUTED|USER)\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']')
    changes = []
    new_lines = []
    for l in lines:
        m = pattern.match(l)
        if m:
            key = m.group(1)
            new_val = CONFORT.get(key)
            if new_val:
                new_lines.append(f'{key} = "{new_val}"\n')
                changes.append(f"{key}: -> {new_val}")
                continue
        new_lines.append(l)
    return new_lines, changes


def patch_appearance(lines):
    src = "".join(lines)
    if 'set_appearance_mode("light")' in src:
        return lines, "deja light"
    if 'set_appearance_mode("dark")' in src:
        lines = [l.replace('set_appearance_mode("dark")',
                           'set_appearance_mode("light")') for l in lines]
        return lines, "dark -> light"
    if "set_appearance_mode" not in src:
        for i, l in enumerate(lines):
            if "import customtkinter" in l:
                lines.insert(i + 1, "\n")
                lines.insert(i + 2, 'ctk.set_appearance_mode("light")\n')
                lines.insert(i + 3, 'ctk.set_default_color_theme("blue")\n')
                return lines, "ajoute light par defaut"
        return lines, "customtkinter introuvable"
    return lines, "inchange"


def patch():
    log("=" * 72)
    log("PATCH GUI - palette Confort Visuel (meilleure pour les yeux)")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)

    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    log("[1/3] Menu compact...")
    new_lines, msg = replace_menu(lines)
    if new_lines is not None:
        lines = new_lines
        log(f"  -> {msg}")

    log("[2/3] Application palette Confort Visuel...")
    lines, changes = patch_theme(lines)
    for c in changes:
        log(f"  -> {c}")

    log("[3/3] Mode CustomTkinter light...")
    lines, msg = patch_appearance(lines)
    log(f"  -> {msg}")

    src2 = "".join(lines)
    TARGET.write_text(src2, encoding="utf-8")

    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src2)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Restaure.")
        return 1

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(patch())