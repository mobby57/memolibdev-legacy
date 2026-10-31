"""tools_shell.py - Outil run_command avec liste blanche."""
from __future__ import annotations
import subprocess
from pathlib import Path
from tool_use import Tool, ToolRegistry


# ALLOWED_BINARIES supprime : run_command retourne BLOQUE en tete.
# Le module n'est plus enregistre (assistant_v2 ne l'importe plus).


def register_shell_tools(root: Path, registry: ToolRegistry):
    root = Path(root).resolve()

    def run_command(command: str, timeout: int = 60) -> str:
        return "BLOQUE: execution shell directe desactivee."

    registry.register(Tool(
        "run_command",
        "Execute une commande autorisee (npm, git, pytest, python, tsc)",
        {"type": "object",
         "properties": {
             "command": {"type": "string"},
             "timeout": {"type": "integer"}},
         "required": ["command"]},
        run_command))
