#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_fix.py - Corrige contraste titre/boutons + repositionne le menu."""
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


# --- Palette a CONTRASTE ELEVE ----------------------------------------
PALETTE = {
    "BG":     "#f0f0eb",   # creme tres clair (pas blanc pur)
    "CARD":   "#ffffff",   # bulles blanches (contraste net)
    "ACCENT": "#1e40af",   # bleu FONCE - lisible sur creme
    "TEXT":   "#111827",   # presque noir - contraste 15:1
    "MUTED":  "#4b5563",   # gris moyen-FONCE - lisible
    "USER":   "#1d4ed8",   # bleu fonce bulle utilisateur
}


# --- Menu compact et repositionne --------------------------------------
NEW_MENU = '''        try:
            ctk.CTkOptionMenu(
                header,
                values=self._available_models or [DEFAULT_MODEL],
                variable=self.model_var,
                width=120,
                height=26,
                font=ctk.CTkFont(size=9),
                dropdown_font=ctk.CTkFont(size=9),
            ).pack(side="right", padx=(2, 4))
        except Exception:
            pass
'''


def replace_palette(lines):
    pattern = re.compile(
        r'^(BG|CARD|ACCENT|TEXT|MUTED|USER)\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']')
    changes = []
    new_lines = []
    for l in lines:
        m = pattern.match(l)
        if m:
            key = m.group(1)
            new_val = PALETTE.get(key)
            if new_val:
                new_lines.append(f'{key} = "{new_val}"\n')
                changes.append(f"{key}: -> {new_val}")
                continue
        new_lines.append(l)
    return new_lines, changes


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


def force_text_color_on_buttons(lines):
    """
    Pour chaque CTkButton dont le texte est en couleur faible,
    ajoute ou remplace text_color=TEXT.
    """
    changes = 0
    out = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if "CTkButton(" in l:
            # Chercher la fin du statement (jusqu'a ")" en equilibre)
            block_start = i
            depth = 0
            block_end = i
            for j in range(i, min(len(lines), i + 30)):
                depth += lines[j].count("(") - lines[j].count(")")
                if depth <= 0 and "(" in lines[j]:
                    block_end = j
                    break
            block = "".join(lines[block_start:block_end + 1])

            has_text_color = "text_color" in block
            has_bg = "fg_color" in block

            # Si pas de text_color, forcer
            if not has_text_color:
                # Ajouter text_color=TEXT avant la derniere )
                # Trouver la ligne avec la ) fermante
                last = lines[block_end]
                if last.rstrip().endswith(")"):
                    # Chercher la ligne avec "text=" pour y accoler
                    inserted = False
                    for k in range(block_end, block_start - 1, -1):
                        if "text=" in lines[k] and lines[k].rstrip().endswith(","):
                            lines[k] = lines[k].rstrip() + " text_color=TEXT,\n"
                            inserted = True
                            changes += 1
                            break
                    if not inserted:
                        # Inserer une ligne avant la )
                        indent = " " * (len(lines[block_end]) - len(lines[block_end].lstrip()))
                        lines.insert(block_end, f"{indent}    text_color=TEXT,\n")
                        changes += 1
        i += 1
    return lines, changes


def force_title_color(lines):
    """
    Cherche le titre MemoLibDev (font size >= 20) et force text_color=ACCENT
    ou TEXT selon ce qui existe deja.
    """
    changes = 0
    for i, l in enumerate(lines):
        if '"MemoLibDev"' in l or "'MemoLibDev'" in l:
            # C'est probablement le titre. Chercher la ligne du bloc.
            block_start = max(0, i - 5)
            block_end = min(len(lines), i + 8)
            block = "".join(lines[block_start:block_end])
            if "CTkLabel" in block:
                # Forcer text_color=ACCENT si pas de text_color
                if "text_color=" not in block:
                    # Ajouter sur la meme ligne
                    for k in range(block_start, block_end):
                        if "MemoLibDev" in lines[k]:
                            if lines[k].rstrip().endswith(","):
                                lines[k] = lines[k].rstrip() + " text_color=ACCENT,\n"
                                changes += 1
                            break
    return lines, changes


def patch():
    log("=" * 72)
    log("PATCH GUI FIX - contraste + agencement")
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

    # [1] Palette
    log("[1/4] Palette a contraste eleve...")
    lines, changes = replace_palette(lines)
    for c in changes:
        log(f"  -> {c}")

    # [2] Menu compact
    log("[2/4] Menu compact (120x26)...")
    rng = find_menu_block(lines)
    if rng:
        start, end = rng
        new_menu = NEW_MENU.splitlines(keepends=True)
        lines = lines[:start] + new_menu + lines[end:]
        log("  -> menu remplace")
    else:
        log("  -> menu introuvable")

    # [3] Forcer text_color sur les boutons
    log("[3/4] Forcage text_color sur les CTkButton...")
    lines, n = force_text_color_on_buttons(lines)
    log(f"  -> {n} boutons patche(s)")

    # [4] Forcer couleur titre
    log("[4/4] Forcage couleur du titre MemoLibDev...")
    lines, n = force_title_color(lines)
    log(f"  -> {n} titre(s) patche(s)")

    # Ecriture
    src2 = "".join(lines)
    TARGET.write_text(src2, encoding="utf-8")

    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src2)
        log("  Syntaxe OK.")
    except SyntaxError as e:
        log(f"  ERREUR ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("  Fichier restaure.")
        return 1

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log()
    log("Attendu :")
    log("  - Titre MemoLibDev en BLEU FONCE lisible")
    log("  - Boutons (Ecrire, Erreurs, ...) avec texte NOIR")
    log("  - (aucun projet) en gris moyen-fonce")
    log("  - Menu compact a droite, pas de chevauchement")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(patch())