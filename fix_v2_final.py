#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_v2_final.py - 2 fixs : reinit index projet + prompt avec outils."""
from __future__ import annotations
import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

GUI = ROOT / "memolibdev_gui_v4.py"
V2 = ROOT / "assistant_v2.py"


def log(m=""):
    print(m, flush=True)


# =====================================================================
# FIX 1 - GUI : reinit index au choix de projet
# =====================================================================
CHOOSE_OLD = '''        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
'''

CHOOSE_NEW = '''        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
            self._reinit_v2_for_project(Path(d))
'''

REINIT_METHOD = '''    def _reinit_v2_for_project(self, project_root: Path):
        """Reconstruit l'index et l'assistant V2 pour le projet choisi."""
        if not getattr(self, "_v2_ready", False):
            return
        try:
            self._system("Reconstruction de l'index...")
            self._v2_index = CodebaseIndex(project_root.resolve())
            n = self._v2_index.build()
            stats = self._v2_index.stats()
            self._v2_assistant = AssistantV2(
                project_root.resolve(),
                index=self._v2_index,
            )
            self._system(
                f"Index : {stats['files']} fichiers, "
                f"{stats['symbols']} symboles"
            )
        except Exception as e:
            self._system(f"Reconstruction index echouee : {e}")

'''


def fix_gui(src: str) -> tuple[str, list[str]]:
    changes = []

    # 1. Patch _choose_project
    if "_reinit_v2_for_project" in src:
        changes.append("reinit deja present")
    elif CHOOSE_OLD in src:
        src = src.replace(CHOOSE_OLD, CHOOSE_NEW, 1)
        changes.append("_choose_project patche")
    else:
        changes.append("ANCRE _choose_project introuvable")

    # 2. Ajouter la methode _reinit_v2_for_project avant v2_chat
    if "def _reinit_v2_for_project" in src:
        changes.append("methode _reinit deja presente")
    else:
        anchor = "    def v2_chat(self, text: str) -> bool:"
        if anchor in src:
            src = src.replace(anchor, REINIT_METHOD + anchor, 1)
            changes.append("methode _reinit_v2_for_project ajoutee")
        else:
            changes.append("ANCRE v2_chat introuvable")

    return src, changes


# =====================================================================
# FIX 2 - assistant_v2.py : prompt avec outils
# =====================================================================
NEW_PROMPT = '''SYSTEM_PROMPT = """Tu es MemoLibDev, un assistant de code local.

CONTEXTE : tu travailles sur le projet indique par l'utilisateur.
Tu as un index de ce projet et des outils pour interagir avec.

OUTILS DISPONIBLES :
- read_file(path) : lire un fichier du projet
- list_files(pattern) : lister les fichiers
- find_symbol(name) : chercher une fonction/classe
- write_file(path, content) : creer/remplacer un fichier
- edit_file(path, old, new) : remplacer un motif
- delete_file(path) : supprimer un fichier
- run_command(cmd) : executer une commande autorisee

REGLES :
- Reponds TOUJOURS en francais, directement, sans demander la permission.
- Pour lire un fichier, emets :
<tool_call>{"name": "read_file", "args": {"path": "agent_loop.py"}}</tool_call>
- Ne dis JAMAIS "je ne peux pas lire les fichiers". Tu PEUX.
- Reponds en 2-5 phrases concises.
- Si tu ne sais pas, dis-le au lieu d'inventer."""'''


def fix_v2(src: str) -> tuple[str, list[str]]:
    changes = []

    if "OUTILS DISPONIBLES :" in src and "read_file(path)" in src:
        changes.append("prompt deja patche")
        return src, changes

    m = re.search(r'SYSTEM_PROMPT\s*=\s*""".*?"""', src, re.DOTALL)
    if m is None:
        changes.append("ANCRE SYSTEM_PROMPT introuvable")
        return src, changes

    src = re.sub(
        r'SYSTEM_PROMPT\s*=\s*""".*?"""',
        NEW_PROMPT,
        src,
        count=1,
        flags=re.DOTALL,
    )
    changes.append("SYSTEM_PROMPT remplace")
    return src, changes


# =====================================================================
# Main
# =====================================================================
def main():
    log("=" * 72)
    log("FIX V2 FINAL - reinit index + prompt avec outils")
    log("=" * 72)
    log()

    BK.mkdir(exist_ok=True)
    log(f"Backups : {BK.name}/")
    log()

    # --- FIX 1 : GUI ---
    log("[1/2] Patch memolibdev_gui_v4.py...")
    if not GUI.exists():
        log(f"  ERREUR : {GUI.name} introuvable.")
        return 1
    src = GUI.read_text(encoding="utf-8")
    src_new, changes = fix_gui(src)
    for c in changes:
        log(f"  -> {c}")
    if "ANCRE" in " ".join(changes):
        log("  ROLLBACK : ancre introuvable.")
        return 1
    try:
        ast.parse(src_new)
    except SyntaxError as e:
        log(f"  ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        return 1
    shutil.copy2(GUI, BK / GUI.name)
    GUI.write_text(src_new, encoding="utf-8")
    log("  Syntaxe OK. Ecrit.")
    log()

    # --- FIX 2 : assistant_v2.py ---
    log("[2/2] Patch assistant_v2.py...")
    if not V2.exists():
        log(f"  ERREUR : {V2.name} introuvable.")
        return 1
    src = V2.read_text(encoding="utf-8")
    src_new, changes = fix_v2(src)
    for c in changes:
        log(f"  -> {c}")
    if "ANCRE" in " ".join(changes):
        log("  ROLLBACK : ancre introuvable.")
        return 1
    try:
        ast.parse(src_new)
    except SyntaxError as e:
        log(f"  ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        return 1
    shutil.copy2(V2, BK / V2.name)
    V2.write_text(src_new, encoding="utf-8")
    log("  Syntaxe OK. Ecrit.")
    log()

    # --- Verif finale ---
    log("Verifications finales :")
    checks = [
        (GUI, "_reinit_v2_for_project", "GUI : methode _reinit"),
        (GUI, "self._reinit_v2_for_project(Path(d))", "GUI : appel dans _choose_project"),
        (V2, "OUTILS DISPONIBLES", "V2 : prompt avec outils"),
        (V2, "read_file(path)", "V2 : outil read_file listé"),
    ]
    all_ok = True
    for path, needle, label in checks:
        content = path.read_text(encoding="utf-8")
        if needle in content:
            log(f"  [OK] {label}")
        else:
            log(f"  [MANQUE] {label}")
            all_ok = False

    log()
    if all_ok:
        log("=" * 72)
        log("PATCHS APPLIQUES")
        log("=" * 72)
        log()
        log("Relancez :")
        log("  $env:PYTHONIOENCODING = 'utf-8'")
        log("  python .\\memolibdev_gui_v4.py")
        log()
        log("Test 1 : Choisir projet -> Desktop\\memolib")
        log("         Envoyer : 'Bonjour, resume ce projet'")
        log("         Doit mentionner 'memolib' (pas MemoLibDev)")
        log()
        log("Test 2 : Envoyer : 'Lis le README.md et resume-le'")
        log("         Doit emettre un <tool_call> read_file")
        log()
        log("Rollback :")
        log(f"  Copy-Item {BK.name}\\{GUI.name} .\\{GUI.name} -Force")
        log(f"  Copy-Item {BK.name}\\{V2.name} .\\{V2.name} -Force")
    else:
        log("PROBLEME : certaines verifications ont echoue.")
        log("Restaurez depuis le backup.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())