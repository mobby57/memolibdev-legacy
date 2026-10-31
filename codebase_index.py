"""codebase_index.py - Indexeur robuste Python + TS/JS."""
from __future__ import annotations
import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# Dossiers à ignorer partout
IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env",
    ".patch_backups", "_legacy_document_engine", ".claude",
    "node_modules", ".next", "dist", "build", "coverage",
    ".turbo", "out", ".cache", ".parcel-cache",
    "target", "bin", "obj",
}

# Extensions de source
SOURCE_EXTS = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


@dataclass
class Symbol:
    kind: str
    name: str
    file: str
    line: int
    docstring: str = ""
    signature: str = ""


@dataclass
class FileIndex:
    path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    error: str | None = None


class CodebaseIndex:
    """Indexe les symboles Python et TS/JS d'un codebase."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.files: dict[str, FileIndex] = {}

    def _iter_sources(self):
        for dirpath, dirnames, filenames in os.walk(
            self.root, onerror=lambda e: None
        ):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for name in filenames:
                if name.startswith("."):
                    continue
                if ".d.ts" in name or ".min." in name:
                    continue
                if any(name.endswith(ext) for ext in SOURCE_EXTS):
                    yield Path(dirpath) / name

    def build(self, max_files: int = 5000) -> int:
        count = 0
        for f in sorted(self._iter_sources()):
            if count >= max_files:
                break
            try:
                self._index_file(f)
                count += 1
            except Exception:
                continue
        return count

    def _index_file(self, path: Path):
        try:
            rel = str(path.relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return
        if path.suffix.lower() == ".py":
            self._index_py(path, rel)
        else:
            self._index_js(path, rel)

    def _index_py(self, path: Path, rel: str):
        try:
            src = path.read_text(encoding="utf-8")
        except Exception as e:
            self.files[rel] = FileIndex(rel, error=f"read: {e}")
            return
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            self.files[rel] = FileIndex(rel, error=f"SyntaxError L{e.lineno}")
            return
        fi = FileIndex(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    fi.imports.append(n.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for n in node.names:
                    fi.imports.append(f"{mod}.{n.name}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fi.symbols.append(Symbol(
                    kind="function", name=node.name, file=rel,
                    line=node.lineno,
                    docstring=(ast.get_docstring(node) or "")[:200],
                    signature=f"def {node.name}()"))
            elif isinstance(node, ast.ClassDef):
                fi.symbols.append(Symbol(
                    kind="class", name=node.name, file=rel,
                    line=node.lineno,
                    docstring=(ast.get_docstring(node) or "")[:200],
                    signature=f"class {node.name}"))
        self.files[rel] = fi

    def _index_js(self, path: Path, rel: str):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            self.files[rel] = FileIndex(rel, error=f"read: {e}")
            return
        if not src.strip():
            self.files[rel] = FileIndex(rel)
            return
        fi = FileIndex(rel)
        for m in re.finditer(
            r'^\s*import\s+.*?from\s+["\']([^"\']+)["\']', src, re.M
        ):
            fi.imports.append(m.group(1))
        for m in re.finditer(
            r'^\s*import\s+["\']([^"\']+)["\']', src, re.M
        ):
            fi.imports.append(m.group(1))
        pats = [
            (r'export\s+(?:async\s+)?function\s+(\w+)', "function"),
            (r'export\s+class\s+(\w+)', "class"),
            (r'export\s+interface\s+(\w+)', "interface"),
            (r'export\s+type\s+(\w+)', "type"),
            (r'export\s+const\s+(\w+)', "const"),
            (r'^(?:async\s+)?function\s+(\w+)', "function"),
            (r'^class\s+(\w+)', "class"),
            (r'^interface\s+(\w+)', "interface"),
            (r'^type\s+(\w+)', "type"),
        ]
        for pat, kind in pats:
            for m in re.finditer(pat, src, re.M):
                line_no = src[:m.start()].count("\n") + 1
                fi.symbols.append(Symbol(
                    kind=kind, name=m.group(1), file=rel,
                    line=line_no, signature=f"{kind} {m.group(1)}"))
        self.files[rel] = fi

    def find_symbol(self, name: str) -> list[Symbol]:
        results = []
        for fi in self.files.values():
            for s in fi.symbols:
                if name.lower() in s.name.lower():
                    results.append(s)
        return results

    def find_in_file(self, rel_path: str):
        return self.files.get(rel_path)

    def search(self, term: str, limit: int = 20) -> list[dict]:
        results = []
        t = term.lower()
        for rel, fi in self.files.items():
            if t in rel.lower():
                results.append({"file": rel, "match": "path"})
            for s in fi.symbols:
                if t in s.name.lower():
                    results.append({
                        "file": rel, "line": s.line,
                        "kind": s.kind, "name": s.name,
                        "signature": s.signature, "match": "symbol",
                    })
                    if len(results) >= limit:
                        return results[:limit]
        return results[:limit]

    def stats(self) -> dict:
        total_symbols = sum(len(fi.symbols) for fi in self.files.values())
        errors = [f for f, fi in self.files.items() if fi.error]
        return {
            "files": len(self.files),
            "symbols": total_symbols,
            "errors": len(errors),
        }

    def save(self, path: Path):
        data = {
            "root": str(self.root),
            "files": {
                rel: {
                    "imports": fi.imports,
                    "symbols": [
                        {"kind": s.kind, "name": s.name, "line": s.line,
                         "signature": s.signature, "docstring": s.docstring}
                        for s in fi.symbols
                    ],
                    "error": fi.error,
                }
                for rel, fi in self.files.items()
            },
        }
        Path(path).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "CodebaseIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        idx = cls(Path(data["root"]))
        for rel, fd in data["files"].items():
            fi = FileIndex(rel, imports=fd["imports"], error=fd.get("error"))
            for s in fd["symbols"]:
                fi.symbols.append(Symbol(
                    kind=s["kind"], name=s["name"], file=rel,
                    line=s["line"], docstring=s.get("docstring", ""),
                    signature=s.get("signature", "")))
            idx.files[rel] = fi
        return idx