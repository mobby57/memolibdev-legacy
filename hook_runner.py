"""hook_runner.py - Execute les hooks pre_task / post_task d'un projet.

Contrat :
- Hook = script Python dans <project>/.memolib/hooks/{kind}_*.py
- Recoit JSON sur stdin : {"diff": str, "target": str, ...}
- Retourne JSON sur stdout : {"ok": bool, "reason": str}
- Fail-closed : crash, timeout, exit code != 0, JSON invalide, ok=false
  => le hook bloque l'operation appeleuse.

Convention :
- pre_task : avant l'application D5.9. ok=false => aucune ecriture.
- post_task : dans le verify D5.9. ok=false => rollback automatique.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


HOOK_TIMEOUT_SECONDS = 300


def run_hooks(
    kind: str,
    hook_dir: Path,
    context: dict,
    timeout: int = HOOK_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Execute tous les hooks {kind}_*.py. Fail-closed sur toute erreur.

    Args:
        kind: "pre_task" ou "post_task"
        hook_dir: chemin vers <project>/.memolib/hooks
        context: dict serialise en JSON, envoye sur stdin de chaque hook
        timeout: duree max par hook en secondes

    Returns:
        (ok, reason). ok=True si aucun hook OU si tous reussissent.
    """
    hook_dir = Path(hook_dir)
    if not hook_dir.is_dir():
        return True, f"no {kind} hooks (dir absent: {hook_dir})"

    hooks = sorted(hook_dir.glob(f"{kind}_*.py"))
    if not hooks:
        return True, f"no {kind} hooks"

    payload = json.dumps(context, ensure_ascii=False)
    for hook in hooks:
        try:
            result = subprocess.run(
                [sys.executable, str(hook)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return False, f"{hook.name}: timeout > {timeout}s"
        except (OSError, ValueError) as e:
            return False, f"{hook.name}: {type(e).__name__}: {e}"

        if result.returncode != 0:
            err = (result.stderr or "").strip()[:300]
            return False, f"{hook.name}: exit {result.returncode}: {err}"

        raw = (result.stdout or "").strip()
        if not raw:
            return False, f"{hook.name}: empty stdout"

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            return False, f"{hook.name}: invalid JSON ({e}): {raw[:200]}"

        if not isinstance(data, dict) or "ok" not in data:
            return False, f"{hook.name}: missing 'ok' field: {raw[:200]}"

        if not data["ok"]:
            reason = str(data.get("reason", "blocked"))[:500]
            return False, f"{hook.name}: {reason}"

    return True, f"{len(hooks)} {kind} hook(s) OK"