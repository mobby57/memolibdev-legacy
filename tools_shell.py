"""tools_shell.py - Outil run_command avec liste blanche."""
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
            return f"[rc={r.returncode}]\n{out[:4000]}"
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
