"""tools_verify.py - Verification deterministe apres ecriture."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from tool_use import Tool, ToolRegistry


def register_verify_tools(root: Path, registry: ToolRegistry):
    root = Path(root).resolve()

    def _safe(p: str):
        target = (root / p).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return None
        return target

    def verify_file(path: str) -> dict:
        """Verifie la syntaxe d'un fichier. Retourne {ok, kind, message}."""
        p = _safe(path)
        if p is None:
            return {"ok": False, "kind": "error", "message": "chemin hors projet"}
        if not p.is_file():
            return {"ok": False, "kind": "error", "message": "fichier introuvable"}
        ext = p.suffix.lower()
        if ext == ".py":
            cmd = [sys.executable, "-m", "py_compile", str(p)]
        elif ext == ".json":
            cmd = [sys.executable, "-m", "json.tool", str(p)]
        else:
            return {"ok": True, "kind": "skipped",
                    "message": f"extension {ext} non verifiee"}
        try:
            result = subprocess.run(
                cmd, cwd=str(root),
                capture_output=True, text=True, timeout=30,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "kind": "timeout", "message": "verification > 30s"}
        except OSError as exc:
            return {"ok": False, "kind": "error",
                    "message": f"{type(exc).__name__}: {exc}"}
        if result.returncode == 0:
            return {"ok": True, "kind": ext.lstrip("."), "message": "syntaxe OK"}
        err = (result.stderr or result.stdout or "").strip()
        return {"ok": False, "kind": ext.lstrip("."),
                "message": err[-2000:] if err else "(aucune sortie)"}

    registry.register(Tool(
        "verify_file",
        "Verifie la syntaxe d'un fichier (.py, .json). Retourne {ok, message}.",
        {"type": "object",
         "properties": {"path": {"type": "string"}},
         "required": ["path"]},
        verify_file))
