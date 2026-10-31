#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_v042.py
-----------
Corrige _appr dans test_v042_mandatory_binding.py :
  approved_at="t"  ->  datetime.now(utc).isoformat()

Idempotent, backup avant ecriture.
"""
from pathlib import Path
import re
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "test_v042_mandatory_binding.py"

OLD_LINE = '    base = dict(approved=True, approver="alice", approved_at="t",\n'
NEW_BLOCK = (
    '    import datetime as _dt\n'
    '    base = dict(approved=True, approver="alice",\n'
    '                approved_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),\n'
)


def main() -> int:
    print("=" * 72)
    print("FIX_V042 - timestamp ISO frais pour _appr")
    print("=" * 72)

    if not TARGET.exists():
        print(f"ERREUR : {TARGET.name} introuvable")
        return 1

    src = TARGET.read_text(encoding="utf-8")

    if "approved_at=_dt.datetime.now" in src:
        print("Deja patche. Rien a faire.")
        return 0

    if OLD_LINE not in src:
        print("ERREUR : ligne cible introuvable.")
        print(f"Cherche : {OLD_LINE!r}")
        return 1

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = ROOT / f".patch_backups_{ts}"
    bk.mkdir(exist_ok=True)
    shutil.copy2(TARGET, bk / TARGET.name)
    print(f"Backup -> {bk.name}/{TARGET.name}")

    # Remplacement
    src = src.replace(OLD_LINE, NEW_BLOCK, 1)
    TARGET.write_text(src, encoding="utf-8")
    print("Patch applique : approved_at <- datetime.now(utc).isoformat()")
    print()
    print("Relancez :")
    print("  python .\\test_v042_mandatory_binding.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())