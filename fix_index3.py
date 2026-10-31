#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_index3.py - Ajoute .ts/.tsx/.js/.jsx a l'indexeur."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "codebase_index.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "EXTENSIONS" in src:
    print("Deja patche.")
    raise SystemExit(0)

# 1. Ajouter la constante EXTENSIONS au debut du fichier (apres les imports)
if "EXTENSIONS = " not in src:
    # Trouver la premiere ligne vide apres les imports
    lines = src.splitlines(keepends=True)
    insert_at = 0
    for i, l in enumerate(lines[:30]):
        if l.startswith("from ") or l.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, "\n")
    lines.insert(insert_at + 1, 'EXTENSIONS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")\n')
    src = "".join(lines)
    print("-> constante EXTENSIONS ajoutee")

# 2. Remplacer le filtre .py dans _safe_iter_py
old_filter = '''            for name in filenames:
                if name.endswith(".py"):
                    yield Path(dirpath) / name
'''
new_filter = '''            for name in filenames:
                if any(name.endswith(ext) for ext in EXTENSIONS):
                    yield Path(dirpath) / name
'''
if old_filter in src:
    src = src.replace(old_filter, new_filter, 1)
    print("-> filtre etendu a .ts/.tsx/.js/.jsx")
else:
    print("ATTENTION : filtre exact introuvable, essai fallback")
    # Fallback : chercher name.endswith(".py")
    if 'if name.endswith(".py"):' in src:
        src = src.replace(
            'if name.endswith(".py"):',
            'if any(name.endswith(ext) for ext in EXTENSIONS):',
            1,
        )
        print("-> filtre remplace (fallback)")

# 3. Verif syntaxe
try:
    ast.parse(src)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src, encoding="utf-8")
print(f"OK - patch applique (backup : {BK.name}/)")