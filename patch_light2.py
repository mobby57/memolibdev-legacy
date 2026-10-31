#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_light2.py - Remet le theme clair (palette Confort Visuel)."""
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
    "ACCENT": "#4a6b8a",
    "TEXT":   "#3a3733",
    "MUTED":  "#8a8479",
    "USER":   "#4d6d8a",
}


def main():
    print("=" * 72)
    print("PATCH LIGHT2 - theme Confort Visuel")
    print("=" * 72)
    print()

    if not TARGET.exists():
        print("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    print(f"Backup -> {BK.name}/{TARGET.name}")
    print()

    # [1] Remplacer les constantes de couleur
    print("[1/2] Remplacement des constantes...")
    pattern = re.compile(
        r'^(BG|CARD|ACCENT|TEXT|MUTED|USER)\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']',
        re.MULTILINE,
    )
    count = 0
    def repl(m):
        nonlocal count
        key = m.group(1)
        count += 1
        return f'{key} = "{PALETTE[key]}"'
    src = pattern.sub(repl, src)
    print(f"  -> {count} constantes remplacees")

    # Si BORDER n'existe pas dans la palette, on le force aussi
    if 'BORDER = ' in src:
        src = re.sub(r'^BORDER\s*=\s*["\']#[0-9a-fA-F]{3,8}["\']',
                     'BORDER = "#d6d1c4"', src, flags=re.MULTILINE)
        print("  -> BORDER ajuste a #d6d1c4")

    # [2] Forcer set_appearance_mode("light")
    print("[2/2] Mode CustomTkinter...")
    if 'set_appearance_mode("dark")' in src:
        src = src.replace('set_appearance_mode("dark")',
                          'set_appearance_mode("light")')
        print("  -> dark -> light")
    elif 'set_appearance_mode("light")' in src:
        print("  -> deja en light")
    elif 'set_appearance_mode' not in src:
        # Injecter apres import customtkinter
        lines = src.splitlines(keepends=True)
        for i, l in enumerate(lines):
            if "import customtkinter" in l:
                lines.insert(i + 1, 'ctk.set_appearance_mode("light")\n')
                lines.insert(i + 2, 'ctk.set_default_color_theme("blue")\n')
                break
        src = "".join(lines)
        print("  -> light ajoute par defaut")

    # Verif syntaxe
    try:
        ast.parse(src)
        print("  Syntaxe OK.")
    except SyntaxError as e:
        print(f"  ERREUR ligne {e.lineno} : {e.msg}")
        shutil.copy2(BK / TARGET.name, TARGET)
        print("  Restaure.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    print()
    print("=" * 72)
    print("PATCH APPLIQUE - theme clair")
    print("=" * 72)
    print()
    print("Relancez : python .\\memolibdev_gui_v4.py")
    print()
    print("Si le titre et les boutons restent peu lisibles,")
    print("c'est que ACCENT ou MUTED ne sont pas utilises sur ces widgets.")
    print("Dans ce cas, envoyez une capture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())