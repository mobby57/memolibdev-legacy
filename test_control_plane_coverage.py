#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_control_plane_coverage.py
------------------------------
Verifie que CONTROL_PLANE_FILES couvre tout fichier contenant les
symboles sensibles (HumanApproval, run_controlled_apply, verify_diff_binding).

Test META : si un nouveau module manipule ces symboles et n'est pas
dans CONTROL_PLANE_FILES, ce test echoue.
"""
from pathlib import Path
import ast
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent_loop import CONTROL_PLANE_FILES

PASS, FAIL = [], []

def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))

SENSITIVE_SYMBOLS = (
    "HumanApproval",
    "run_controlled_apply",
    "verify_diff_binding",
    "verify_approval_freshness",
    "d59_controlled_apply",
)

# Fichiers volontairement hors liste : tests, scripts one-shot, legacy.
EXEMPT_PREFIXES = ("test_", "apply_", "patch_", "prepare_", "fix_", "secure_")
EXEMPT_DIRS = ("_legacy_document_engine", ".patch_backups_", ".git", "__pycache__")

def is_exempt(path: Path) -> bool:
    if any(part in EXEMPT_DIRS for part in path.parts):
        return True
    if any(path.name.startswith(p) for p in EXEMPT_PREFIXES):
        return True
    return False

def uses_sensitive(path: Path) -> set[str]:
    try:
        src = path.read_text(encoding="utf-8")
    except Exception:
        return set()
    found = set()
    for sym in SENSITIVE_SYMBOLS:
        if sym in src:
            found.add(sym)
    return found

def main() -> int:
    print("=" * 72)
    print("CONTROL PLANE COVERAGE")
    print("=" * 72)
    print()

    missing = []
    for py in sorted(ROOT.glob("*.py")):
        if is_exempt(py):
            continue
        if py.name in CONTROL_PLANE_FILES:
            continue
        used = uses_sensitive(py)
        if used:
            missing.append((py.name, sorted(used)))

    ok("aucun fichier sensible hors CONTROL_PLANE_FILES",
       not missing,
       "; ".join(f"{n}={u}" for n, u in missing) or "tous couverts")

    # Verifier que chaque entree de la liste existe bien
    absent = [n for n in CONTROL_PLANE_FILES if not (ROOT / n).exists()]
    ok("toutes les entrees de CONTROL_PLANE_FILES existent",
       not absent, ", ".join(absent) or "ok")

    print()
    print("=" * 72)
    print(f"RESULTAT : {len(PASS)} PASS / {len(FAIL)} FAIL")
    if FAIL:
        print("ECHECS :", ", ".join(FAIL))
    print("=" * 72)
    return 0 if not FAIL else 1

if __name__ == "__main__":
    raise SystemExit(main())
