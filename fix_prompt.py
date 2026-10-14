#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_prompt.py - Remplace SYSTEM_PROMPT par une version directive."""
from __future__ import annotations
import ast
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "assistant_v2.py"
BK = ROOT / f".patch_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

NEW_PROMPT = '''SYSTEM_PROMPT = """Tu es MemoLibDev, un assistant de code local.

REGLES :
- Reponds TOUJOURS directement en francais, sans demander la permission.
- Si on te demande d'expliquer du code, fais-le avec ce que tu sais.
- N'utilise les outils QUE si on te demande explicitement de lire ou modifier un fichier.
- Ne dis JAMAIS "je vais lire" puis t'arreter. Soit tu le fais, soit tu reponds.
- Reponds en 2-5 phrases concises."""'''


def log(m=""):
    print(m, flush=True)


def main():
    log("=" * 72)
    log("FIX PROMPT - SYSTEM_PROMPT directif")
    log("=" * 72)
    log()

    if not TARGET.exists():
        log(f"ERREUR : {TARGET.name} introuvable.")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    # Chercher le SYSTEM_PROMPT actuel
    m = re.search(r'SYSTEM_PROMPT\s*=\s*""".*?"""', src, re.DOTALL)
    if m is None:
        log("ERREUR : SYSTEM_PROMPT introuvable.")
        log("Cherchez-le manuellement dans assistant_v2.py")
        return 1

    old_prompt = m.group(0)
    log("SYSTEM_PROMPT actuel (premieres lignes) :")
    for l in old_prompt.splitlines()[:5]:
        log("  " + l)
    log()

    # Verifier s'il est deja patche
    if "Reponds TOUJOURS directement" in src:
        log("Deja patche. Rien a faire.")
        return 0

    # Backup
    BK.mkdir(exist_ok=True)
    shutil.copy2(TARGET, BK / TARGET.name)
    log(f"Backup -> {BK.name}/{TARGET.name}")

    # Remplacer
    new_src = re.sub(
        r'SYSTEM_PROMPT\s*=\s*""".*?"""',
        NEW_PROMPT,
        src,
        count=1,
        flags=re.DOTALL,
    )

    # Verif syntaxe
    try:
        ast.parse(new_src)
        log("Syntaxe OK.")
    except SyntaxError as e:
        log(f"ERREUR syntaxe ligne {e.lineno} : {e.msg}")
        log("Restauration...")
        shutil.copy2(BK / TARGET.name, TARGET)
        return 1

    TARGET.write_text(new_src, encoding="utf-8")
    log()
    log("=" * 72)
    log("PATCH APPLIQUE")
    log("=" * 72)
    log()
    log("Nouveau SYSTEM_PROMPT :")
    for l in NEW_PROMPT.splitlines():
        log("  " + l)
    log()

    # Test automatique
    log("Lancement du test V2...")
    log()

    test_code = (
        "from assistant_v2 import AssistantV2; "
        "from codebase_index import CodebaseIndex; "
        "from pathlib import Path; "
        "idx=CodebaseIndex(Path('.').resolve()); "
        "idx.build(); "
        "a=AssistantV2(Path('.').resolve(), index=idx); "
        "print('--- TEST 1 : bonjour ---'); "
        "print(a.chat('Bonjour, qui es-tu ?')); "
        "print(); "
        "print('--- TEST 2 : explication ---'); "
        "print(a.chat('Explique en 2 phrases ce que fait agent_loop.py'))"
    )

    try:
        r = subprocess.run(
            [sys.executable, "-c", test_code],
            cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        log("--- Sortie du test ---")
        log(r.stdout or "")
        if r.stderr:
            log("--- Erreurs ---")
            log(r.stderr)
    except subprocess.TimeoutExpired:
        log("TIMEOUT (300s). Le modele est peut-etre lent au chargement.")
    except Exception as e:
        log(f"Erreur test : {type(e).__name__}: {e}")

    log()
    log("=" * 72)
    log("PROCHAINES ETAPES")
    log("=" * 72)
    log()
    log("Si les 2 tests repondent en francais naturel :")
    log("  1. Router V2 dans la GUI (patch manuel de 5 lignes dans _on_send)")
    log("  2. Relancer la GUI : python .\\memolibdev_gui_v4.py")
    log("  3. Tester : 'bonjour'")
    log()
    log("Rollback : git checkout -- assistant_v2.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())