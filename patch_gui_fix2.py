#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_fix2.py - Repare le menu (grid au lieu de pack)."""
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


def main():
    print("=" * 72)
    print("PATCH GUI FIX2 - repare le menu (grid dans le header)")
    print("=" * 72)
    print()

    if not TARGET.exists():
        print(f"ERREUR : {TARGET.name} introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    print(f"Backup -> {BK.name}/{TARGET.name}")
    print()

    # [1] Supprimer le bloc menu_row casse (insere par patch_gui_layout)
    print("[1/3] Suppression du bloc menu_row casse...")
    pattern = re.compile(
        r"\n        # --- Bandeau Modele \(ligne dediee\) ---.*?except Exception:\n            pass\n",
        re.DOTALL,
    )
    src, n = pattern.subn("\n", src)
    print(f"  -> {n} bloc(s) supprime(s)")

    # [2] Inserer le menu dans le header (colonne 4), avant self.chat
    print("[2/3] Insertion du menu dans le header (grid, colonne 4)...")
    anchor = "        self.chat = ctk.CTkScrollableFrame(self, fg_color=BG, corner_radius=0)"
    menu_block = (
        "        # --- Menu des modeles (dans le header, colonne 4) ---\n"
        "        try:\n"
        "            ctk.CTkOptionMenu(\n"
        "                header,\n"
        "                values=self._available_models or [DEFAULT_MODEL[:28]],\n"
        "                variable=self.model_var,\n"
        "                width=160, height=30,\n"
        "                font=ctk.CTkFont(size=9),\n"
        "                dropdown_font=ctk.CTkFont(size=9),\n"
        "            ).grid(row=0, column=4, padx=(0, 16), pady=16)\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
    )
    if anchor in src:
        src = src.replace(anchor, menu_block + anchor, 1)
        print("  -> menu insere (colonne 4 du header)")
    else:
        print("  ERREUR : ancre 'self.chat' introuvable.")
        shutil.copy2(BK / TARGET.name, TARGET)
        print("  Restaure.")
        return 1

    # [3] Verif syntaxe
    print("[3/3] Verification syntaxique...")
    try:
        ast.parse(src)
        print("  Syntaxe OK.")
    except SyntaxError as e:
        print(f"  ERREUR ligne {e.lineno} : {e.msg}")
        print(f"  {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        print("  Restaure.")
        return 1

    TARGET.write_text(src, encoding="utf-8")

    print()
    print("=" * 72)
    print("PATCH APPLIQUE")
    print("=" * 72)
    print()
    print("Relancez : python .\\memolibdev_gui_v4.py")
    print()
    print("Attendu :")
    print("  - GUI s'ouvre sans erreur")
    print("  - Menu des modeles dans le header (a droite des boutons)")
    print("  - Plus de chevauchement")
    print()
    print("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())