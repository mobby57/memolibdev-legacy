#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""force_v2_routing.py - Force le routage V2 dans _on_send."""
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


V2_ROUTING = '''        # --- V2 : priorite si disponible ---
        if getattr(self, "_v2_ready", False):
            self.entry.delete("1.0", "end")
            if self.v2_chat(text):
                return
        # --- sinon, continuer avec la CLI existante ---
'''


def main():
    log("=" * 72)
    log("FORCE V2 ROUTING")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log("ERREUR : fichier introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    # Est-ce que V2 est deja route ?
    if "_v2_ready" in src and "if self.v2_chat(text)" in src:
        log("V2 est DEJA route dans _on_send.")
        log()
        log("Verification de l'import V2...")
        if "from assistant_v2 import AssistantV2" not in src:
            log("  ERREUR : import AssistantV2 manquant !")
            log("  Le routage existe mais ne peut pas fonctionner.")
        else:
            log("  Import AssistantV2 present.")
        log()
        log("Verification de l'init...")
        if "self._v2_assistant = AssistantV2" not in src:
            log("  ERREUR : init AssistantV2 manquante !")
        else:
            log("  Init presente.")
        log()
        log("Diagnostic : le routage est bien en place.")
        log("Le probleme est ailleurs :")
        log("  - Ollama repond ? (verifiez le terminal 'ollama serve')")
        log("  - V2 a bien demarre ? (message '[V2] Assistant conversationnel pret.')")
        log("  - Modele disponible ? (ollama list)")
        return 0

    log("V2 n'est PAS route dans _on_send. Ajout en cours...")
    log()

    # Backup
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")
    log()

    # Trouver _on_send
    lines = src.splitlines(keepends=True)
    idx_on_send = None
    for i, l in enumerate(lines):
        if re.match(r"\s+def _on_send\(self\):", l):
            idx_on_send = i
            break

    if idx_on_send is None:
        log("ERREUR : _on_send introuvable.")
        return 1

    # Trouver la ligne "if getattr(self, '_identity_check_pending', False):"
    # et inserer le routage V2 juste apres
    insert_at = None
    for i in range(idx_on_send, min(len(lines), idx_on_send + 20)):
        if "_identity_check_pending" in lines[i]:
            insert_at = i + 1
            break

    if insert_at is None:
        # Fallback : insere juste apres la definition
        insert_at = idx_on_send + 1

    # Detecter l'indentation
    indent = ""
    for ch in lines[insert_at]:
        if ch in " \t":
            indent += ch
        else:
            break

    # Preparer le bloc a inserer (avec l'indentation correcte)
    block_lines = []
    for line in V2_ROUTING.splitlines(keepends=True):
        if line.strip():
            block_lines.append(indent + line)
        else:
            block_lines.append(line)

    # Inserer
    lines.insert(insert_at, "".join(block_lines))
    src2 = "".join(lines)

    # Verif syntaxe
    try:
        ast.parse(src2)
        log("Syntaxe OK.")
    except SyntaxError as e:
        log(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        log(f"  {e.text}")
        shutil.copy2(BK / TARGET.name, TARGET)
        log("Restaure.")
        return 1

    TARGET.write_text(src2, encoding="utf-8")

    log()
    log("=" * 72)
    log("ROUTAGE V2 AJOUTE")
    log("=" * 72)
    log()
    log("Relancez : python .\\memolibdev_gui_v4.py")
    log()
    log("Verifiez au demarrage que le terminal affiche :")
    log("  [V2] Assistant conversationnel pret.")
    log()
    log("Si V2 est pret, toute question part a Ollama.")
    log("Sinon, la CLI prend le relais (mode degrade).")
    return 0


if __name__ == "__main__":
    sys.exit(main())