"""tools_run.py - Execution controlee de commandes (whitelist stricte)."""
from __future__ import annotations
import shlex
import subprocess
import sys
from pathlib import Path
from tool_use import Tool, ToolRegistry


# Chaque entree est un tuple de tokens. Une commande est autorisee si
# ses N premiers tokens correspondent exactement a l'une de ces entrees.
WHITELIST = (
    ("python", "-m", "pytest"),
    ("python", "-m", "py_compile"),
    ("python", "-m", "json.tool"),
    ("python", "-m", "unittest"),
    ("pytest",),
    ("npx", "vitest"),
    ("npx", "tsc"),
    ("npx", "playwright"),
    ("npm", "test"),
    ("npm", "run"),
    ("npm", "ls"),
    ("git", "status"),
    ("git", "diff"),
    ("git", "log"),
    ("git", "show"),
    ("git", "branch"),
)

TIMEOUT_SECONDS = 120
MAX_OUTPUT = 8000


def _split(cmd: str) -> list[str] | None:
    if not isinstance(cmd, str) or not cmd.strip() or len(cmd) > 500:
        return None
    if any(ch in cmd for ch in ("|", ">", "<", "&", ";", "`", "$(")):
        return None
    try:
        tokens = shlex.split(cmd, posix=False)
    except ValueError:
        return None
    return [t.strip('"').strip("'") for t in tokens if t]


def _is_allowed(tokens: list[str]) -> bool:
    for prefix in WHITELIST:
        n = len(prefix)
        if len(tokens) >= n and tuple(tokens[:n]) == prefix:
            return True
    return False


def register_run_tools(root: Path, registry: ToolRegistry,
                       coder_mode: bool = False):
    root = Path(root).resolve()

    def run_command(cmd: str) -> dict:
        if not coder_mode:
            return {"ok": False, "message": "mode coder requis"}
        tokens = _split(cmd)
        if not tokens:
            return {"ok": False, "message": "commande vide ou interdite"}
        if not _is_allowed(tokens):
            return {
                "ok": False,
                "message": f"commande non autorisee : {tokens[:3]}",
            }
        try:
            result = subprocess.run(
                tokens, cwd=str(root),
                capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": f"timeout > {TIMEOUT_SECONDS}s"}
        except (OSError, ValueError) as exc:
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        out = (result.stdout or "")[-MAX_OUTPUT:]
        err = (result.stderr or "")[-MAX_OUTPUT:]
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": out,
            "stderr": err,
        }

    registry.register(Tool(
        "run_command",
        "Execute une commande de test/build/lint (whitelist stricte).",
        {"type": "object",
         "properties": {"cmd": {"type": "string"}},
         "required": ["cmd"]},
        run_command))
