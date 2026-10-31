#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_index2.py - os.walk robuste (continue apres erreur)."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "codebase_index.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "_safe_iter_py" in src:
    print("Deja patche.")
    raise SystemExit(0)

# Chercher la fonction build existante
OLD_MARKER = "    def build(self, max_files: int = 500) -> int:"
if OLD_MARKER not in src:
    print("ERREUR : 'def build' introuvable")
    raise SystemExit(1)

# Trouver le debut du bloc build
idx = src.index(OLD_MARKER)

# Trouver la fin : prochain "    def " au meme niveau
after = src[idx + len(OLD_MARKER):]
next_def = after.find("\n    def ")
if next_def == -1:
    # fin du fichier ou de la classe
    end_idx = len(src)
else:
    end_idx = idx + len(OLD_MARKER) + next_def + 1

# Bloc de remplacement
NEW_BUILD = '''    def _safe_iter_py(self):
        """Itere sur tous les .py du projet en continuant apres erreur."""
        import os
        for dirpath, dirnames, filenames in os.walk(self.root, onerror=lambda e: None):
            # Filtrer les dossiers a ignorer
            dirnames[:] = [
                d for d in dirnames
                if d not in (".git", "__pycache__", ".venv", "venv",
                             ".patch_backups", "_legacy_document_engine",
                             ".claude", "node_modules")
            ]
            for name in filenames:
                if name.endswith(".py"):
                    yield Path(dirpath) / name

    def build(self, max_files: int = 500) -> int:
        count = 0
        for py in sorted(self._safe_iter_py()):
            if count >= max_files:
                break
            try:
                self._index_file(py)
                count += 1
            except (OSError, FileNotFoundError, PermissionError):
                continue
        return count
'''

src2 = src[:idx] + NEW_BUILD + src[end_idx:]

try:
    ast.parse(src2)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    print(f"  {e.text}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src2, encoding="utf-8")
print(f"OK - patch applique (backup : {BK.name}/)")