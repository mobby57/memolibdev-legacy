"""tools_file.py - Outils fichiers pour AssistantV2."""
from __future__ import annotations
from pathlib import Path
from tool_use import Tool, ToolRegistry


def register_file_tools(root: Path, registry: ToolRegistry):
    """Enregistre write_file, edit_file, delete_file sur un projet."""
    root = Path(root).resolve()

    def _safe(p: str):
        target = (root / p).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def write_file(path: str, content: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        action = "modifie" if existed else "cree"
        return f"OK: {path} {action} ({len(content)} octets)"

    def edit_file(path: str, old: str, new: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        src = p.read_text(encoding="utf-8")
        if old not in src:
            return f"ERREUR: motif introuvable dans {path}"
        count = src.count(old)
        if count > 1:
            return f"ERREUR: motif present {count} fois dans {path} (ambigu)"
        new_src = src.replace(old, new, 1)
        p.write_text(new_src, encoding="utf-8")
        return f"OK: {path} ({len(src)} -> {len(new_src)} octets)"

    def delete_file(path: str) -> str:
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        p.unlink()
        return f"OK: {path} supprime"

    registry.register(Tool(
        "write_file",
        "Cree ou remplace un fichier dans le projet",
        {"type": "object",
         "properties": {
             "path": {"type": "string"},
             "content": {"type": "string"}},
         "required": ["path", "content"]},
        write_file))

    registry.register(Tool(
        "edit_file",
        "Remplace un motif unique dans un fichier",
        {"type": "object",
         "properties": {
             "path": {"type": "string"},
             "old": {"type": "string"},
             "new": {"type": "string"}},
         "required": ["path", "old", "new"]},
        edit_file))

    registry.register(Tool(
        "delete_file",
        "Supprime un fichier (irreversible)",
        {"type": "object",
         "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        delete_file))
