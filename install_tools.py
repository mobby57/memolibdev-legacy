#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
install_tools.py
----------------
Installe les outils de developpement dans MemoLibDev :
  - tools_file.py   : write_file, edit_file, delete_file
  - tools_shell.py  : run_command (liste blanche)
  - patche assistant_v2.py (enregistrement + prompt systeme)

Idempotent, backup avant ecriture, rollback si syntaxe cassee.
"""
from __future__ import annotations

import ast
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def log(m=""):
    print(m, flush=True)


# =====================================================================
# 1. tools_file.py
# =====================================================================
TOOLS_FILE = '''"""tools_file.py - Outils fichiers pour AssistantV2."""
from __future__ import annotations
from pathlib import Path
from tool_use import Tool, ToolRegistry


def register_file_tools(root: Path, registry: ToolRegistry):
    """Enregistre write_file, edit_file, delete_file sur un projet."""
    root = Path(root).resolve()

    def _safe(p: str):
        target = (root / p).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def write_file(path: str, content: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        action = "modifie" if existed else "cree"
        return f"OK: {path} {action} ({len(content)} octets)"

    def edit_file(path: str, old: str, new: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        src = p.read_text(encoding="utf-8")
        if old not in src:
            return f"ERREUR: motif introuvable dans {path}"
        count = src.count(old)
        if count > 1:
            return f"ERREUR: motif present {count} fois dans {path} (ambigu)"
        new_src = src.replace(old, new, 1)
        p.write_text(new_src, encoding="utf-8")
        return f"OK: {path} ({len(src)} -> {len(new_src)} octets)"

    def delete_file(path: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        p.unlink()
        return f"OK: {path} supprime"

    registry.register(Tool(
        "write_file",
        "Cree ou remplace un fichier dans le projet",
        {"type": "object",
         "properties": {
             "path": {"type": "string"},
             "content": {"type": "string"}},
         "required": ["path", "content"]},
        write_file))

    registry.register(Tool(
        "edit_file",
        "Remplace un motif unique dans un fichier",
        {"type": "object",
         "properties": {
             "path": {"type": "string"},
             "old": {"type": "string"},
             "new": {"type": "string"}},
         "required": ["path", "old", "new"]},
        edit_file))

    registry.register(Tool(
        "delete_file",
        "Supprime un fichier (irreversible)",
        {"type": "object",
         "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        delete_file))
'''


# =====================================================================
# 2. tools_shell.py
# =====================================================================
TOOLS_SHELL = '''"""tools_shell.py - Outil run_command avec liste blanche."""
from __future__ import annotations
import subprocess
from pathlib import Path
from tool_use import Tool, ToolRegistry


ALLOWED_BINARIES = {
    "npm", "node", "npx", "pnpm", "yarn",
    "python", "python3", "pip",
    "git",
    "pytest", "vitest", "tsc", "playwright", "jest",
    "make", "docker",
}


def register_shell_tools(root: Path, registry: ToolRegistry):
    root = Path(root).resolve()

    def run_command(command: str, timeout: int = 60) -> str:
        parts = command.strip().split()
        if not parts:
            return "ERREUR: commande vide"
        binary = parts[0].lower()
        for suffix in (".exe", ".cmd", ".bat", ".ps1"):
            if binary.endswith(suffix):
                binary = binary[: -len(suffix)]
        if binary not in ALLOWED_BINARIES:
            return (f"ERREUR: commande non autorisee ({binary}). "
                    f"Autorisees: {sorted(ALLOWED_BINARIES)}")
        try:
            r = subprocess.run(
                parts, cwd=root, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=timeout, shell=False,
            )
            out = (r.stdout or "") + (r.stderr or "")
            return f"[rc={r.returncode}]\\n{out[:4000]}"
        except subprocess.TimeoutExpired:
            return f"ERREUR: timeout ({timeout}s)"
        except FileNotFoundError:
            return f"ERREUR: binaire introuvable ({binary})"
        except Exception as e:
            return f"ERREUR {type(e).__name__}: {e}"

    registry.register(Tool(
        "run_command",
        "Execute une commande autorisee (npm, git, pytest, python, tsc)",
        {"type": "object",
         "properties": {
             "command": {"type": "string"},
             "timeout": {"type": "integer"}},
         "required": ["command"]},
        run_command))
'''


# =====================================================================
# 3. Patch assistant_v2.py
# =====================================================================
NEW_SYSTEM_PROMPT = '''SYSTEM_PROMPT = """Tu es MemoLibDev, un assistant de code local et securise.
Tu reponds en francais.

OUTILS DISPONIBLES :
- read_file(path) : lire un fichier
- list_files(pattern) : lister les fichiers
- find_symbol(name) : chercher une fonction/classe
- write_file(path, content) : creer/remplacer un fichier
- edit_file(path, old, new) : remplacer un motif unique
- delete_file(path) : supprimer un fichier
- run_command(command) : executer une commande autorisee

REGLES :
1. Utilise read_file AVANT edit_file pour verifier le contenu actuel.
2. Pour un nouveau fichier : write_file.
3. Pour modifier une ligne : edit_file (old doit etre unique).
4. Tu ne modifies JAMAIS sans validation explicite de l'utilisateur.
5. Emets les appels d'outils ainsi :
<tool_call>{"name": "read_file", "args": {"path": "src/app.ts"}}</tool_call>

Attends le resultat avant d'emettre un nouvel appel.
Explique brievement ce que tu fais entre chaque appel."""'''


def patch_assistant():
    return 'BLOQUE: installateur historique désactivé; aucune modification appliquée.'


# =====================================================================
# Main
# =====================================================================
def main():
    return "BLOQUE: install_tools.py désactivé pour éviter la réactivation d'outils permissifs."


if __name__ == "__main__":
    sys.exit(main())