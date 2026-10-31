#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_contrast.py - Force text_color=TEXT sur les CTkButton + hover clair."""
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

# Couleurs pour le texte et le hover en theme clair
TEXT_COLOR = "TEXT"          # nom de la constante dans le fichier
HOVER_LIGHT = "#e5e0d5"      # beige un peu plus fonce pour hover
HOVER_DARK_OLD = "#21262d"   # ancienne couleur hover (theme sombre)


def log(m=""):
    print(m, flush=True)


def patch_ctk_buttons(src: str) -> tuple[str, int]:
    """
    Parcourt le code et, pour chaque 'ctk.CTkButton(' :
    - si text_color absent -> ajoute text_color=TEXT
    - si text_color="white"/"#fff"/"#ffffff" -> remplace par TEXT
    """
    lines = src.splitlines(keepends=True)
    out = []
    changes = 0
    i = 0
    while i < len(lines):
        l = lines[i]
        if "CTkButton(" in l and "self." not in l.split("CTkButton")[0][-10:]:
            # On entre dans un appel CTkButton. Chercher la fin de l'appel.
            depth = 0
            block_start = i
            block_end = i
            for j in range(i, min(len(lines), i + 40)):
                depth += lines[j].count("(") - lines[j].count(")")
                if "(" in lines[j] and depth <= 0:
                    block_end = j
                    break
            block = lines[block_start:block_end + 1]
            block_str = "".join(block)

            # Deja un text_color ?
            has_text_color = re.search(r"text_color\s*=", block_str)
            if has_text_color:
                # Remplacer si blanc
                new_block = []
                for bl in block:
                    bl2 = re.sub(
                        r'text_color\s*=\s*["\'](#fff|#ffffff|white|#FFF|#FFFFFF|WHITE)["\']',
                        f'text_color={TEXT_COLOR}',
                        bl,
                    )
                    if bl2 != bl:
                        changes += 1
                    new_block.append(bl2)
                out.extend(new_block)
            else:
                # Ajouter text_color=TEXT juste avant la parenthese fermante
                # On cherche la derniere ligne du bloc
                last_idx = len(block) - 1
                new_block = list(block)
                # Trouver la ligne avec ")" fermante
                for k in range(last_idx, -1, -1):
                    if new_block[k].rstrip().endswith(")"):
                        # Ajouter une ligne avant
                        indent = re.match(r"^(\s*)", new_block[k]).group(1)
                        # Si la ligne contient deja quelque chose avant )
                        before = new_block[k].rstrip()
                        # Cas simple : la ligne est "        )"
                        if before.strip() == ")":
                            new_block.insert(k, f"{indent}    text_color={TEXT_COLOR},\n")
                        else:
                            # Ajouter sur la meme ligne, avant la )
                            new_block[k] = re.sub(
                                r"\)(\s*)$",
                                f", text_color={TEXT_COLOR})\\1",
                                new_block[k],
                            )
                        changes += 1
                        break
                out.extend(new_block)

            i = block_end + 1
        else:
            out.append(l)
            i += 1

    return "".join(out), changes


def patch_hover_colors(src: str) -> tuple[str, int]:
    """Remplace tous les hover_color='#21262d' par une couleur claire."""
    pattern = re.compile(r'hover_color\s*=\s*["\']#21262d["\']')
    new_src, n = pattern.subn(f'hover_color="{HOVER_LIGHT}"', src)
    return new_src, n


def patch_border_colors(src: str) -> tuple[str, int]:
    """S'assure que BORDER est clair."""
    if 'BORDER = ' not in src:
        return src, 0
    pattern = re.compile(
        r'^BORDER\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']',
        re.MULTILINE,
    )
    new_src, n = pattern.subn('BORDER = "#d6d1c4"', src)
    return new_src, n


def main():
    log("=" * 72)
    log("PATCH CONTRAST - text_color sur boutons + hover clair")
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

    # [1] CTkButton : forcer text_color=TEXT
    log("[1/3] Forcage text_color sur CTkButton...")
    src, n1 = patch_ctk_buttons(src)
    log(f"  -> {n1} bouton(s) patche(s)")

    # [2] hover_color sombre -> clair
    log("[2/3] Remplacement des hover_color sombres...")
    src, n2 = patch_hover_colors(src)
    log(f"  -> {n2} hover_color remplace(s)")

    # [3] BORDER clair
    log("[3/3] Ajustement de BORDER...")
    src, n3 = patch_border_colors(src)
    log(f"  -> {n3} BORDER ajuste(s)")

    # Ecriture + verif
    TARGET.write_text(src, encoding="utf-8")
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

    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log()
    log("Attendu :")
    log("  - Boutons du header : texte lisible")
    log("  - Boutons de suggestions : texte lisible")
    log("  - Hover clair au survol")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())