#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_gui_layout.py - Deplace le menu sur une ligne dediee + tronque les noms."""
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


# 1. Tronquer les noms de modeles dans la liste (pour la variable)
TRUNCATE_LOAD = '''        # Charger la liste des modeles Ollama (noms tronques)
        try:
            import json as _json
            _req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
            with urllib.request.urlopen(_req, timeout=3) as _r:
                _data = _json.loads(_r.read().decode("utf-8"))
            _names = [m["name"] for m in _data.get("models", [])]
            # Tronquer pour l'affichage
            self._available_models = [n[:28] + "..." if len(n) > 28 else n for n in _names]
            self._model_names_map = dict(zip(self._available_models, _names))
            if not self._available_models:
                self._available_models = [DEFAULT_MODEL[:28]]
                self._model_names_map = {DEFAULT_MODEL[:28]: DEFAULT_MODEL}
        except Exception:
            self._available_models = [DEFAULT_MODEL[:28]]
            self._model_names_map = {DEFAULT_MODEL[:28]: DEFAULT_MODEL}
'''


def main():
    log("=" * 72)
    log("PATCH GUI LAYOUT - menu sur ligne dediee + noms tronques")
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

    # [1] Remplacer le bloc de chargement pour tronquer les noms
    log("[1/3] Remplacement du chargement des modeles (troncature)...")
    src2 = "".join(lines)
    # Chercher tout le bloc "Charger la liste des modeles"
    old_pattern = re.compile(
        r"        # Charger la liste des modeles Ollama.*?self\._available_models = \[DEFAULT_MODEL\]\n",
        re.DOTALL,
    )
    m = old_pattern.search(src2)
    if m:
        src2 = src2[:m.start()] + TRUNCATE_LOAD + src2[m.end():]
        log("  -> noms tronques a 28 caracteres")
    else:
        log("  -> bloc introuvable, skip")

    lines = src2.splitlines(keepends=True)

    # [2] Supprimer le menu actuel du header
    log("[2/3] Suppression du menu dans le header...")
    src3 = "".join(lines)
    menu_pattern = re.compile(
        r"        try:\n"
        r"            ctk\.CTkOptionMenu\(\n"
        r"                header,.*?except Exception:\n"
        r"            pass\n",
        re.DOTALL,
    )
    if menu_pattern.search(src3):
        src3 = menu_pattern.sub("", src3)
        log("  -> menu retire du header")
    else:
        log("  -> menu header introuvable, skip")

    lines = src3.splitlines(keepends=True)

    # [3] Ajouter un bandeau menu sous le header (avant le chat)
    log("[3/3] Ajout d'un bandeau 'Modele' sous le header...")

    MENU_ROW = '''        # --- Bandeau Modele (ligne dediee) ---
        menu_row = ctk.CTkFrame(self, fg_color="transparent")
        menu_row.pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(
            menu_row, text="Modele :", text_color=MUTED,
            font=ctk.CTkFont(size=10, weight="bold")
        ).pack(side="left", padx=(0, 6))

        try:
            ctk.CTkOptionMenu(
                menu_row,
                values=self._available_models or [DEFAULT_MODEL[:28]],
                variable=self.model_var,
                width=280,
                height=26,
                font=ctk.CTkFont(size=10),
                dropdown_font=ctk.CTkFont(size=10),
            ).pack(side="left")
        except Exception:
            pass
'''

    # Chercher la ligne "self.chat = ctk.CTkScrollableFrame" pour inserer avant
    for i, l in enumerate(lines):
        if "self.chat = ctk.CTkScrollableFrame" in l:
            lines.insert(i, MENU_ROW)
            log(f"  -> bandeau insere avant la ligne {i + 1}")
            break
    else:
        log("  -> 'self.chat' introuvable, insertion ailleurs")
        # Fallback : apres la ligne qui contient "self.busy = False"
        for i, l in enumerate(lines):
            if l.strip() == "self.busy = False":
                lines.insert(i + 1, MENU_ROW)
                log(f"  -> bandeau insere apres 'self.busy' (ligne {i + 2})")
                break

    # Ecriture
    src4 = "".join(lines)
    TARGET.write_text(src4, encoding="utf-8")

    log()
    log("Verification syntaxique...")
    try:
        ast.parse(src4)
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
    log("  - Bandeau 'Modele : [...]' sous le titre")
    log("  - Boutons 'Choisir projet' / 'Sauver log' a droite, visibles")
    log("  - Plus de chevauchement")
    log()
    log("Rollback : git checkout -- memolibdev_gui_v4.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())