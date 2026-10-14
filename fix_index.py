#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_index.py - Ignore les erreurs scandir dans CodebaseIndex."""
from pathlib import Path
import ast
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "codebase_index.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

src = TARGET.read_text(encoding="utf-8")

if "_safe_rglob" in src:
    print("Deja patche.")
    raise SystemExit(0)

OLD = '''    def build(self, max_files: int = 500) -> int:
        count = 0
        for py in sorted(self.root.rglob("*.py")):
            if any(p in py.parts for p in
                   (".git", "__pycache__", ".venv", "venv",
                    ".patch_backups", "_legacy_document_engine")):
                continue
            if count >= max_files:
                break
            self._index_file(py)
            count += 1
        return count
'''

NEW = '''    def _safe_rglob(self, pattern: str):
        """rglob qui ignore les erreurs de permission / liens casses."""
        try:
            for p in self.root.rglob(pattern):
                try:
                    p.is_file()
                except (OSError, FileNotFoundError):
                    continue
                yield p
        except (OSError, FileNotFoundError, PermissionError):
            return

    def build(self, max_files: int = 500) -> int:
        count = 0
        for py in sorted(self._safe_rglob("*.py")):
            if any(p in py.parts for p in
                   (".git", "__pycache__", ".venv", "venv",
                    ".patch_backups", "_legacy_document_engine",
                    ".claude", "node_modules")):
                continue
            if count >= max_files:
                break
            try:
                self._index_file(py)
                count += 1
            except (OSError, FileNotFoundError, PermissionError):
                continue
        return count
'''

if OLD not in src:
    print("ERREUR : bloc build introuvable")
    raise SystemExit(1)

src2 = src.replace(OLD, NEW, 1)

try:
    ast.parse(src2)
    print("Syntaxe OK")
except SyntaxError as e:
    print(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
    raise SystemExit(1)

BK.mkdir(exist_ok=True)
shutil.copy2(TARGET, BK / TARGET.name)
TARGET.write_text(src2, encoding="utf-8")
print(f"OK - patch applique (backup : {BK.name}/)")
print()
print("Test :")
print('  python -c "from codebase_index import CodebaseIndex; from pathlib import Path; idx=CodebaseIndex(Path(r\'C:\\Users\\moros\\Desktop\\memolib\')); n=idx.build(); print(f\'{n} fichiers indexes\'); print(idx.stats())"')