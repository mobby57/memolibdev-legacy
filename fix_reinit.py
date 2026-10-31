#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_reinit.py - Reconstruit l'index V2 au changement de projet."""
from pathlib import Path
import re
import shutil
import ast
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "memolibdev_gui_v4.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "_reinit_v2_for_project" in src:
    print("Deja patche.")
    raise SystemExit(0)

# 1. Remplacer le bloc _choose_project
old_choose = '''        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
'''

new_choose = '''        d = filedialog.askdirectory(title="Choisir le dossier de code")
        if d:
            self.project_path.set(d)
            self._system(f"Projet : {d}")
            self._reinit_v2_for_project(Path(d))
'''

if old_choose in src:
    src = src.replace(old_choose, new_choose, 1)
    print("-> _choose_project patche")
else:
    print("ERREUR : bloc _choose_project introuvable")
    raise SystemExit(1)

# 2. Ajouter la methode _reinit_v2_for_project avant v2_chat
reinit = '''    def _reinit_v2_for_project(self, project_root: Path):
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

anchor = "    def v2_chat(self, text: str) -> bool:"
if anchor in src:
    src = src.replace(anchor, reinit + anchor, 1)
    print("-> methode _reinit_v2_for_project ajoutee")
else:
    print("ERREUR : ancre 'def v2_chat' introuvable")
    raise SystemExit(1)

# Verif syntaxe
try:
    ast.parse(src)
    print("-> Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    raise SystemExit(1)

# Backup + ecriture
BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src, encoding="utf-8")
print(f"-> Ecrit (backup : {BK.name}/)")

# Verif finale
final = TARGET.read_text(encoding="utf-8")
ok1 = "_reinit_v2_for_project" in final
ok2 = "self._reinit_v2_for_project(Path(d))" in final
print()
print("Verification :")
print(f"  [{'OK' if ok1 else 'MANQUE'}] methode _reinit")
print(f"  [{'OK' if ok2 else 'MANQUE'}] appel dans _choose_project")
print()
print("Relancez : python .\\memolibdev_gui_v4.py")