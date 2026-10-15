"""tools_file.py - Outils fichiers. Mode coder optionnel."""
from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path
from tool_use import Tool, ToolRegistry


def register_file_tools(root: Path, registry: ToolRegistry,
                        coder_mode: bool = False):
    """Enregistre write_file, edit_file, delete_file.

    Si coder_mode=False (defaut) : les 3 outils renvoient BLOQUE.
    Si coder_mode=True : ecriture autorisee, backup automatique dans
    .coder_backups/<timestamp>/ et log dans .coder_log.txt.
    """
    root = Path(root).resolve()
    backups_dir = root / ".coder_backups"
    log_path = root / ".coder_log.txt"

    def _safe(p: str):
        target = (root / p).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def _backup_if_exists(target: Path) -> str | None:
        if not target.exists():
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        rel = target.relative_to(root)
        dest_dir = backups_dir / ts
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dest)
        return str(dest.relative_to(root))

    def _log(action: str, path: str, backup_ref: str | None):
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"{ts}\t{action}\t{path}"
        if backup_ref:
            line += f"\tbackup={backup_ref}"
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def write_file(path: str, content: str) -> str:
        if not coder_mode:
            return "BLOQUE: ecriture desactivee (mode coder requis)."
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        backup_ref = _backup_if_exists(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
        action = "modifie" if existed else "cree"
        _log(action, path, backup_ref)
        return f"OK: {path} {action} ({len(content)} octets)"

    def edit_file(path: str, old: str, new: str) -> str:
        if not coder_mode:
            return "BLOQUE: edition desactivee (mode coder requis)."
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
        backup_ref = _backup_if_exists(p)
        new_src = src.replace(old, new, 1)
        p.write_text(new_src, encoding="utf-8")
        _log("edit", path, backup_ref)
        return f"OK: {path} ({len(src)} -> {len(new_src)} octets)"

    def delete_file(path: str) -> str:
        if not coder_mode:
            return "BLOQUE: suppression desactivee (mode coder requis)."
        p = _safe(path)
        if p is None:
            return f"ERREUR: chemin hors projet ({path})"
        if not p.exists():
            return f"ERREUR: {path} introuvable"
        backup_ref = _backup_if_exists(p)
        p.unlink()
        _log("delete", path, backup_ref)
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
