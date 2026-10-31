"""test_steering_offline.py - Test offline de _load_steering_files (aucun reseau).

Ne touche jamais Ollama, n'instancie jamais AssistantV2. Teste uniquement
le helper de chargement des steering files sur 7 cas.

Executer manuellement :
    python test_steering_offline.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from assistant_v2 import _load_steering_files


PASS, FAIL = [], []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    tag = "PASS" if cond else "FAIL"
    line = f"  [{tag}] {name}"
    if detail:
        line += f" :: {detail}"
    print(line)


def main() -> int:
    print("=" * 72)
    print("OFFLINE TEST - _load_steering_files")
    print("=" * 72)

    tmp = Path(tempfile.mkdtemp(prefix="memolib-steering-"))
    try:
        # S1 : dossier .memolib/steering absent
        r = _load_steering_files(tmp)
        ok("S1 dir absent -> []", r == [])

        # S2 : dossier present mais vide
        sd = tmp / ".memolib" / "steering"
        sd.mkdir(parents=True)
        r = _load_steering_files(tmp)
        ok("S2 dir vide -> []", r == [])

        # S3 : deux fichiers non vides
        (sd / "b.md").write_text("regle B", encoding="utf-8")
        (sd / "a.md").write_text("regle A", encoding="utf-8")
        r = _load_steering_files(tmp)
        ok("S3 deux fichiers -> 2", len(r) == 2, f"n={len(r)}")
        ok("S4 tri alphabetique", len(r) == 2 and r[0][0] == "a.md" and r[1][0] == "b.md")

        # S5 : fichier vide/whitespace ignore
        (sd / "c.md").write_text("   \n  \n", encoding="utf-8")
        r = _load_steering_files(tmp)
        ok("S5 fichier vide ignore", len(r) == 2, f"n={len(r)}")

        # S6 : fichier non-.md ignore
        (sd / "d.txt").write_text("pas un md", encoding="utf-8")
        r = _load_steering_files(tmp)
        ok("S6 fichier non-md ignore", len(r) == 2, f"n={len(r)}")

        # S7 : contenu strip des espaces
        (sd / "a.md").write_text("  \n  regle A  \n  ", encoding="utf-8")
        r = _load_steering_files(tmp)
        ok("S7 contenu strip", len(r) >= 1 and r[0][1] == "regle A")

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RESULTAT : {len(PASS)} PASS / {len(FAIL)} FAIL")
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())