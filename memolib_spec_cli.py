"""memolib_spec_cli.py - CLI de generation de specs Flutter via Ollama local.

Usage :
    python memolib_spec_cli.py "ajouter un ecran de login" --model qwen2.5-coder
    python memolib_spec_cli.py "..." --root ../mon_projet_flutter --slug auth-login

Ecrit .memolib/specs/<slug>/{requirements,design,tasks}.md dans <root>.
Fail-closed : si l'un des appels LLM renvoie une erreur ou du vide,
RuntimeError et aucun fichier n'est ecrit pour cette etape.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spec_engine import generate_spec, LLMCall
from streaming import chat_once


def make_llm_call(
    model: str, host: str,
    temperature: float = 0.2, timeout: int = 600,
    num_predict: int | None = 4096,
) -> LLMCall:
    """Adaptateur chat_once -> LLMCall(system, user) -> str.

    chat_once renvoie un dict {'role': ..., 'content': ...} et NE raise PAS
    sur erreur reseau/HTTP : il met '[ERREUR ...]' dans content. On detecte
    et on raise pour que spec_engine echoue proprement au lieu d'ecrire un
    fichier contenant un message d'erreur.
    """
    def llm_call(system: str, user: str) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = chat_once(
            messages=messages,
            model=model,
            host=host,
            temperature=temperature,
            timeout=timeout,
            num_predict=num_predict,
        )
        content = (result or {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("reponse LLM vide")
        if content.lstrip().startswith("[ERREUR"):
            raise RuntimeError(content.strip())
        return content
    return llm_call


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Genere requirements/design/tasks Flutter via Ollama.",
    )
    ap.add_argument("prompt", help="Description libre de la feature")
    ap.add_argument("--model", default="qwen2.5-coder",
                    help="Modele Ollama (defaut: qwen2.5-coder)")
    ap.add_argument("--host", default="http://127.0.0.1:11434",
                    help="URL Ollama (defaut: http://127.0.0.1:11434)")
    ap.add_argument("--root", default=".",
                    help="Racine du projet cible (defaut: repertoire courant)")
    ap.add_argument("--slug", default=None,
                    help="Slug du dossier de spec (defaut: derive du prompt)")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--timeout", type=int, default=600,
                    help="Timeout par appel LLM en secondes (defaut: 600)")
    args = ap.parse_args(argv)

    llm = make_llm_call(args.model, args.host, args.temperature, args.timeout, 4096)
    try:
        result = generate_spec(
            Path(args.root), args.prompt, llm, slug=args.slug,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"ECHEC : {exc}", file=sys.stderr)
        return 1

    print(f"OK : {result.spec_dir}")
    for name in (result.requirements_path, result.design_path, result.tasks_path):
        print(f"  - {name.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())