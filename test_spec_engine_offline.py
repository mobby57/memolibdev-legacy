"""test_spec_engine_offline.py - Test offline de spec_engine (aucun reseau).

Utilise un llm_call mocke. Valide la chaine generate_spec -> 3 fichiers.
Ne touche jamais Ollama, n'ecrit rien hors d'un dossier temporaire.

Executer manuellement :
    python test_spec_engine_offline.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from spec_engine import generate_spec


PASS, FAIL = [], []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    tag = "PASS" if cond else "FAIL"
    line = f"  [{tag}] {name}"
    if detail:
        line += f" :: {detail}"
    print(line)


def _fake_llm(calls: list[tuple[str, str]]):
    """Retourne un LLMCall qui enregistre les appels et renvoie du texte fixe."""
    counter = {"n": 0}

    def llm(system: str, user: str) -> str:
        counter["n"] += 1
        calls.append((system[:40], user[:40]))
        idx = counter["n"]
        if idx == 1:
            return "# Requirements - demo\n- **REQ-01** - WHEN login, THE SYSTEM SHALL accept.\n"
        if idx == 2:
            return "# Design - demo\n## Architecture\nRiverpod feature-first.\n"
        if idx == 3:
            return "# Tasks - demo\n- [ ] T01 - create login widget (REQ-01)\n"
        return "extra"

    return llm


def _fake_empty(system: str, user: str) -> str:
    return ""


def main() -> int:
    print("=" * 72)
    print("OFFLINE TEST - spec_engine (aucun appel reseau)")
    print("=" * 72)

    tmp = Path(tempfile.mkdtemp(prefix="memolib-spec-test-"))
    calls: list[tuple[str, str]] = []
    llm = _fake_llm(calls)

    try:
        print("\n[C] generate_spec nominal")
        result = generate_spec(tmp, "ajouter un ecran de login", llm, slug="login-test")
        ok("C1 spec_dir cree", result.spec_dir.is_dir())
        ok("C2 requirements.md", result.requirements_path.is_file())
        ok("C3 design.md", result.design_path.is_file())
        ok("C4 tasks.md", result.tasks_path.is_file())
        ok("C5 3 appels LLM", len(calls) == 3, f"n={len(calls)}")
        ok("C6 requirements contient REQ-01",
           "REQ-01" in result.requirements_path.read_text(encoding="utf-8"))
        ok("C7 design contient Riverpod",
           "Riverpod" in result.design_path.read_text(encoding="utf-8"))
        ok("C8 tasks contient T01",
           "T01" in result.tasks_path.read_text(encoding="utf-8"))

        print("\n[E] prompt vide -> ValueError")
        try:
            generate_spec(tmp, "   ", llm)
            ok("E1 prompt vide rejette", False, "pas d'exception")
        except ValueError:
            ok("E1 prompt vide rejette", True)

        print("\n[F] LLM renvoie vide -> pas de fichier ecrit")
        spec_before = tmp / ".memolib" / "specs" / "empty-test"
        try:
            generate_spec(tmp, "feature vide", _fake_empty, slug="empty-test")
            ok("F1 LLM vide rejette", False, "pas d'exception")
        except ValueError:
            ok("F1 LLM vide rejette", True)
            ok("F2 requirements.md absent",
               not (spec_before / "requirements.md").is_file())
            ok("F3 design.md absent",
               not (spec_before / "design.md").is_file())

        print("\n[S] slug par defaut derive du prompt")
        calls2: list[tuple[str, str]] = []
        res2 = generate_spec(tmp, "ajouter un ecran de profil", _fake_llm(calls2))
        ok("S1 slug non vide", bool(res2.slug))
        ok("S2 slug <= 5 mots", len(res2.slug.split("-")) <= 5)

    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 72)
    print(f"RESULTAT : {len(PASS)} PASS / {len(FAIL)} FAIL")
    print("=" * 72)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())