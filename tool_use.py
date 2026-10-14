"""tool_use.py - Function calling Ollama."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    schema: dict
    func: Callable


class ToolRegistry:
    """Registre d'outils avec parsing JSON."""

    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def schemas(self) -> list[dict]:
        return [
            {"type": "function",
             "function": {"name": t.name,
                          "description": t.description,
                          "parameters": t.schema}}
            for t in self.tools.values()
        ]

    def execute(self, name: str, args: dict) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERREUR: outil inconnu {name}"
        try:
            result = tool.func(**args)
            if isinstance(result, (dict, list)):
                return json.dumps(result, ensure_ascii=False, indent=2)
            return str(result)
        except Exception as e:
            return f"ERREUR {type(e).__name__}: {e}"


def parse_tool_calls(text: str) -> list[tuple[str, dict]]:
    """Cherche des appels type <tool_call>{"name": "...", "args": {...}}</tool_call>."""
    calls = []
    pattern = r"<tool_call>(.*?)</tool_call>"
    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1).strip()
        try:
            obj = json.loads(raw)
            name = obj.get("name")
            args = obj.get("args", {})
            if name:
                calls.append((name, args))
        except json.JSONDecodeError:
            continue
    return calls


def make_standard_tools(root: Path, registry: ToolRegistry,
                        index=None):
    """Enregistre les outils standards."""
    root = Path(root).resolve()

    def read_file(path: str) -> str:
        p = (root / path).resolve()
        if not str(p).startswith(str(root)):
            return "ERREUR: chemin hors perimetre"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        return p.read_text(encoding="utf-8")[:8000]

    def list_files(pattern: str = "*.py", limit: int = 50) -> list[str]:
        results = []
        for f in sorted(root.rglob(pattern)):
            if any(p in f.parts for p in (".git", "__pycache__",
                                          ".venv", ".patch_backups")):
                continue
            results.append(str(f.relative_to(root)).replace("\\", "/"))
            if len(results) >= limit:
                break
        return results

    def find_symbol(name: str) -> list[dict]:
        if index is None:
            return []
        return [
            {"file": s.file, "line": s.line, "kind": s.kind,
             "name": s.name, "signature": s.signature}
            for s in index.find_symbol(name)
        ]

    registry.register(Tool(
        "read_file", "Lire un fichier du projet",
        {"type": "object",
         "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        read_file))

    registry.register(Tool(
        "list_files", "Lister les fichiers correspondant a un pattern",
        {"type": "object",
         "properties": {"pattern": {"type": "string"},
                        "limit": {"type": "integer"}}},
        list_files))

    registry.register(Tool(
        "find_symbol", "Chercher un symbole (fonction/classe) par nom",
        {"type": "object",
         "properties": {"name": {"type": "string"}},
         "required": ["name"]},
        find_symbol))
